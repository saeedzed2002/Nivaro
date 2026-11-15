import asyncio
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy import delete, select

from nivaro_cart.domain.mutations import add_standalone, change_line
from nivaro_cart.domain.paid_cleanup import (
    CleanupRejected,
    OrderPaid,
    PaidCart,
    PurchasedLine,
    apply_paid_cleanup,
)
from nivaro_cart.infrastructure.models import Cart, CartGroup, CartLine, Operation, Owner


async def test_paid_cleanup_preserves_edited_line_and_same_sku_spare(database):
    customer, variant, order_id = uuid4(), uuid4(), uuid4()
    async with database.sessions.begin() as db:
        owner = Owner(customer_id=customer)
        db.add(owner)
        await db.flush()
        cart = Cart(owner_id=owner.id, market="ir", currency="IRR")
        other = Cart(owner_id=owner.id, market="international", currency="USD")
        db.add_all([cart, other])
        await db.flush()
        bought, edited = [CartGroup(cart_id=cart.id, name=name) for name in ("Bought", "Edited")]
        db.add_all([bought, edited])
        await db.flush()
        lines = [
            CartLine(
                cart_id=cart.id,
                group_id=group.id,
                slot_key="storage:1",
                variant_id=variant,
                quantity=1,
            )
            for group in (bought, edited)
        ]
        db.add_all(lines)
    try:
        event = OrderPaid(
            event_id=uuid4(),
            event_type="order.paid",
            schema_version=1,
            producer="orders",
            occurred_at=datetime.now(UTC),
            aggregate_id=order_id,
            aggregate_version=4,
            correlation_id=order_id,
            causation_id=None,
            payload=PaidCart(
                cart_id=cart.id,
                cart_version=1,
                customer_id=customer,
                allocation_id=order_id,
                market="ir",
                currency="IRR",
                lines=[
                    PurchasedLine(id=line.id, group_id=line.group_id, version=1, quantity=1)
                    for line in lines
                ],
            ),
        )
        async with database.sessions.begin() as db:
            await change_line(
                db,
                owner_id=owner.id,
                market="ir",
                expected_version=1,
                line_id=lines[1].id,
                quantity=2,
                expected_group_version=1,
            )
        async with database.sessions.begin() as db:
            spare = await add_standalone(
                db,
                owner_id=owner.id,
                market="ir",
                expected_version=2,
                variant_id=variant,
                quantity=1,
            )

        async def consume(message):
            async with database.sessions() as db:
                await apply_paid_cleanup(db, message)

        await asyncio.gather(*(consume(event) for _ in range(4)))
        await consume(event.model_copy(update={"event_id": uuid4()}))
        with pytest.raises(CleanupRejected, match="paid_cleanup.cart_mismatch"):
            await consume(
                event.model_copy(
                    update={"payload": event.payload.model_copy(update={"customer_id": uuid4()})}
                )
            )
        async with database.sessions() as db:
            current = await db.get(Cart, cart.id)
            assert (current.version, current.paid_cleanup_needs_review) == (4, True)
            assert await db.get(CartLine, lines[0].id) is None
            assert await db.get(CartGroup, bought.id) is None
            assert (await db.get(CartLine, lines[1].id)).quantity == 2
            assert (await db.get(CartGroup, edited.id)).version == 2
            assert (await db.get(CartLine, spare.id)).quantity == 1
            assert (await db.get(Cart, other.id)).version == 1
            operation = (
                await db.scalars(select(Operation).where(Operation.owner_id == owner.id))
            ).one()
            assert operation.result["removed_quantity"] == 1
            assert operation.result["preserved_line_ids"] == [str(lines[1].id)]
    finally:
        async with database.sessions.begin() as db:
            await db.execute(delete(Operation).where(Operation.owner_id == owner.id))
            await db.execute(delete(Cart).where(Cart.owner_id == owner.id))
            await db.execute(delete(Owner).where(Owner.id == owner.id))
