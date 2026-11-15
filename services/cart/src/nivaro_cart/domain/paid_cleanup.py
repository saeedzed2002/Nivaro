import hashlib
import json
from typing import Annotated, Literal, Self
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from nivaro_cart.domain.mutations import _lines
from nivaro_cart.infrastructure.models import Cart, CartGroup, Operation, Owner

PAID_QUEUE = "cart.order.paid.v1"
Version = Annotated[int, Field(strict=True, ge=1, le=2147483647)]


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class PurchasedLine(Contract):
    id: UUID
    version: Version
    group_id: UUID | None
    quantity: Annotated[int, Field(strict=True, ge=1, le=20)]


class PaidCart(Contract):
    cart_id: UUID
    cart_version: Version
    customer_id: UUID
    allocation_id: UUID
    market: Literal["ir", "international"]
    currency: Literal["IRR", "USD"]
    lines: Annotated[list[PurchasedLine], Field(min_length=1, max_length=100)]


class OrderPaid(Contract):
    event_id: UUID
    event_type: Literal["order.paid"]
    schema_version: Literal[1]
    producer: Literal["orders"]
    occurred_at: AwareDatetime
    aggregate_id: UUID
    aggregate_version: Version
    correlation_id: UUID
    causation_id: UUID | None
    payload: PaidCart

    @model_validator(mode="after")
    def check_payload(self) -> Self:
        cart = self.payload
        if (self.correlation_id, cart.allocation_id) != (self.aggregate_id, self.aggregate_id):
            raise ValueError("The allocation and correlation must identify the paid order")
        if (cart.market == "ir") != (cart.currency == "IRR"):
            raise ValueError("Cart market and currency must match")
        if len({line.id for line in cart.lines}) != len(cart.lines):
            raise ValueError("Source line IDs must be unique")
        return self


class CleanupRejected(Exception):
    """The paid event conflicts with the cart or a previously handled order."""


async def apply_paid_cleanup(db: AsyncSession, event: OrderPaid) -> None:
    payload = event.payload
    async with db.begin():
        cart = await db.scalar(
            select(Cart)
            .join(Owner, Owner.id == Cart.owner_id)
            .where(
                Cart.id == payload.cart_id,
                Owner.customer_id == payload.customer_id,
                Cart.market == payload.market,
                Cart.currency == payload.currency,
            )
            .with_for_update(of=Cart)
        )
        if cart is None or cart.version < payload.cart_version:
            raise CleanupRejected("paid_cleanup.cart_mismatch")
        key = str(event.aggregate_id)
        snapshot = payload.model_dump(mode="json")
        snapshot["lines"] = sorted(snapshot["lines"], key=lambda line: line["id"])
        fingerprint = hashlib.sha256(
            json.dumps([event.aggregate_version, snapshot], sort_keys=True).encode()
        ).hexdigest()
        prior = await db.scalar(
            select(Operation).where(
                Operation.owner_id == cart.owner_id,
                Operation.kind == "paid_cleanup",
                Operation.key == key,
            )
        )
        if prior is not None:
            if prior.fingerprint != fingerprint:
                raise CleanupRejected("paid_cleanup.replay_conflict")
            return

        current = {line.id: line for line in await _lines(db, cart)}
        touched_groups = set()
        removed = 0
        preserved = []
        for line in payload.lines:
            saved = current.get(line.id)
            if (
                saved is None
                or (saved.version, saved.group_id) != (line.version, line.group_id)
                or saved.quantity < line.quantity
            ):
                preserved.append(str(line.id))
                continue
            removed += line.quantity
            if saved.group_id is not None:
                touched_groups.add(saved.group_id)
            if saved.quantity == line.quantity:
                await db.delete(saved)
                del current[line.id]
            else:
                saved.quantity -= line.quantity
                saved.version += 1

        if touched_groups:
            remaining = {line.group_id for line in current.values()}
            groups = await db.scalars(
                select(CartGroup).where(
                    CartGroup.cart_id == cart.id, CartGroup.id.in_(touched_groups)
                )
            )
            for group in groups:
                if group.id in remaining:
                    group.version += 1
                else:
                    await db.delete(group)
        if removed or (preserved and not cart.paid_cleanup_needs_review):
            cart.version += 1
        cart.paid_cleanup_needs_review = bool(preserved) or cart.paid_cleanup_needs_review
        db.add(
            Operation(
                owner_id=cart.owner_id,
                kind="paid_cleanup",
                key=key,
                fingerprint=fingerprint,
                result={
                    "event_id": str(event.event_id),
                    "removed_quantity": removed,
                    "preserved_line_ids": preserved,
                },
            )
        )
