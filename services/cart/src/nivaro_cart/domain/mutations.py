"""Owner-scoped mutations; callers supply authenticated ownership and a transaction.

These are not browser endpoints. Authorization, catalog checks and API error
mapping belong at the service boundary. All writers, including future merge and
transfer operations, must acquire the cart lock before reading its lines.
"""

from typing import Literal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from nivaro_cart.domain.limits import DEFAULT_LIMITS, Limits, validate_quantities
from nivaro_cart.infrastructure.models import Cart, CartGroup, CartLine

type Market = Literal["ir", "international"]


class CartConflict(Exception):
    def __init__(self, code: str, current_version: int):
        self.code = code
        self.current_version = current_version
        super().__init__(code)


class CartNotFound(Exception):
    """An absent or foreign-owned resource has the same result."""


async def _lock_cart(
    db: AsyncSession, owner_id: UUID, market: Market, expected_version: int
) -> Cart:
    if type(expected_version) is not int or expected_version < 1:
        raise ValueError("cart.invalid_version")
    cart = await db.scalar(
        select(Cart)
        .where(Cart.owner_id == owner_id, Cart.market == market)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if cart is None:
        raise CartNotFound
    if cart.version != expected_version:
        raise CartConflict("cart.version_conflict", cart.version)
    return cart


async def _lines(db: AsyncSession, cart: Cart) -> list[CartLine]:
    return list(
        await db.scalars(
            select(CartLine)
            .where(CartLine.cart_id == cart.id)
            .execution_options(populate_existing=True)
        )
    )


async def add_standalone(
    db: AsyncSession,
    *,
    owner_id: UUID,
    market: Market,
    expected_version: int,
    variant_id: UUID,
    quantity: int,
    limits: Limits = DEFAULT_LIMITS,
) -> CartLine:
    """Add a positive increment to a loose line, never to a matching group line."""
    validate_quantities([(variant_id, quantity)], limits)
    cart = await _lock_cart(db, owner_id, market, expected_version)
    lines = await _lines(db, cart)
    existing = next(
        (line for line in lines if line.group_id is None and line.variant_id == variant_id), None
    )
    proposed = [(line.variant_id, line.quantity) for line in lines]
    if existing is None:
        proposed.append((variant_id, quantity))
    else:
        proposed = [
            (line.variant_id, line.quantity + quantity if line.id == existing.id else line.quantity)
            for line in lines
        ]
    validate_quantities(proposed, limits)
    if existing is None:
        existing = CartLine(cart_id=cart.id, variant_id=variant_id, quantity=quantity)
        db.add(existing)
    else:
        existing.quantity += quantity
        existing.version += 1
    cart.version += 1
    await db.flush()
    return existing


async def _group(
    db: AsyncSession, cart: Cart, group_id: UUID, expected_version: int | None
) -> CartGroup:
    group = await db.scalar(
        select(CartGroup)
        .where(CartGroup.id == group_id, CartGroup.cart_id == cart.id)
        .execution_options(populate_existing=True)
    )
    if group is None:
        raise CartNotFound
    if type(expected_version) is not int or group.version != expected_version:
        raise CartConflict("cart.group_version_conflict", group.version)
    return group


async def change_line(
    db: AsyncSession,
    *,
    owner_id: UUID,
    market: Market,
    expected_version: int,
    line_id: UUID,
    quantity: int | None,
    expected_group_version: int | None = None,
    limits: Limits = DEFAULT_LIMITS,
) -> None:
    """Set a positive quantity; None means explicit removal, never zero."""
    cart = await _lock_cart(db, owner_id, market, expected_version)
    lines = await _lines(db, cart)
    line = next((entry for entry in lines if entry.id == line_id), None)
    if line is None:
        raise CartNotFound
    group = (
        await _group(db, cart, line.group_id, expected_group_version)
        if line.group_id is not None
        else None
    )
    proposed = [(entry.variant_id, entry.quantity) for entry in lines if entry.id != line_id]
    if quantity is not None:
        proposed.append((line.variant_id, quantity))
    validate_quantities(proposed, limits)
    if quantity == line.quantity:
        return
    if quantity is None:
        await db.delete(line)
    else:
        line.quantity = quantity
        line.version += 1
    if group is not None:
        # Evaluations/quotes bind to this revision; removing required slots
        # leaves an incomplete group rather than silently changing its mode.
        group.version += 1
    cart.version += 1
    await db.flush()


async def delete_group(
    db: AsyncSession,
    *,
    owner_id: UUID,
    market: Market,
    expected_version: int,
    group_id: UUID,
    expected_group_version: int,
) -> None:
    cart = await _lock_cart(db, owner_id, market, expected_version)
    group = await _group(db, cart, group_id, expected_group_version)
    await db.delete(group)
    cart.version += 1
    await db.flush()
