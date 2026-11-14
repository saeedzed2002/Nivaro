"""Atomic merge of a proven guest cart into a verified customer cart."""

import hashlib

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from nivaro_cart.domain.errors import CommerceError
from nivaro_cart.domain.limits import Limits, validate_quantities
from nivaro_cart.domain.mutations import CartConflict, Market
from nivaro_cart.domain.ownership import owned_cart
from nivaro_cart.infrastructure.models import Cart, CartGroup, CartLine, Operation, Owner


async def merge_carts(
    db: AsyncSession,
    *,
    guest: Owner,
    customer: Owner,
    source: Cart,
    market: Market,
    source_version: int,
    target_version: int,
    key: str,
    limits: Limits,
) -> dict[str, object]:
    # Both owner locks are already held in customer -> guest order. Bind a key
    # to the authenticated pair, market and exact submitted revisions.
    fingerprint = hashlib.sha256(
        f"{guest.id}:{source.id}:{market}:{source_version}:{target_version}".encode()
    ).hexdigest()
    previous = await db.scalar(
        select(Operation).where(
            Operation.owner_id == customer.id,
            Operation.kind == "merge",
            Operation.key == key,
        )
    )
    if previous is not None:
        if previous.fingerprint != fingerprint:
            raise CommerceError("cart.idempotency_conflict")
        return previous.result

    if source.version != source_version:
        raise CartConflict("cart.guest_version_conflict", source.version)
    target = await owned_cart(db, customer, market)
    if target.version != target_version:
        raise CartConflict("cart.version_conflict", target.version)

    guest_lines = list(await db.scalars(select(CartLine).where(CartLine.cart_id == source.id)))
    target_lines = list(await db.scalars(select(CartLine).where(CartLine.cart_id == target.id)))
    groups = list(await db.scalars(select(CartGroup).where(CartGroup.cart_id == source.id)))
    standalone = {line.variant_id: line for line in target_lines if line.group_id is None}
    coalesced = {
        line.variant_id: line
        for line in guest_lines
        if line.group_id is None and line.variant_id in standalone
    }
    merged_quantities = [
        (
            line.variant_id,
            line.quantity + coalesced[line.variant_id].quantity
            if line.group_id is None and line.variant_id in coalesced
            else line.quantity,
        )
        for line in target_lines
    ]
    moved = [
        line
        for line in guest_lines
        if line.group_id is not None or line.variant_id not in coalesced
    ]
    merged_quantities.extend((line.variant_id, line.quantity) for line in moved)
    validate_quantities(merged_quantities, limits)

    if groups:
        await db.execute(text("SET CONSTRAINTS cart_line_group_owner DEFERRED"))
    for group in groups:
        group.cart_id = target.id
    for line in moved:
        line.cart_id = target.id
    for variant, line in coalesced.items():
        existing = standalone[variant]
        existing.quantity += line.quantity
        existing.version += 1
        if existing.observed_price_version is None:
            existing.observed_price_minor = line.observed_price_minor
            existing.observed_price_version = line.observed_price_version
        await db.delete(line)
    if groups or guest_lines:
        source.version += 1
        target.version += 1
    result: dict[str, object] = {
        "cart_id": str(target.id),
        "version": target.version,
        "guest_version": source.version,
        "moved_groups": len(groups),
        "moved_lines": len(moved),
        "combined_lines": len(coalesced),
    }
    db.add(
        Operation(
            owner_id=customer.id, kind="merge", key=key, fingerprint=fingerprint, result=result
        )
    )
    await db.flush()
    if groups:
        await db.execute(text("SET CONSTRAINTS cart_line_group_owner IMMEDIATE"))
    return result
