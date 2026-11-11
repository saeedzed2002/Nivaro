import asyncio
from uuid import uuid4

import pytest
from sqlalchemy import delete, select, text

from nivaro_cart.domain.limits import Limits
from nivaro_cart.domain.mutations import (
    CartConflict,
    CartNotFound,
    add_standalone,
    change_line,
    delete_group,
)
from nivaro_cart.infrastructure.models import Cart, CartGroup, CartLine, Owner
from nivaro_cart.settings import Settings


@pytest.fixture
async def basket(database):
    async with database.sessions.begin() as db:
        owner = Owner(guest_digest=uuid4().hex * 2)
        db.add(owner)
        await db.flush()
        cart = Cart(owner_id=owner.id, market="ir", currency="IRR")
        other_market = Cart(owner_id=owner.id, market="international", currency="USD")
        db.add_all([cart, other_market])
        await db.flush()
        groups = [CartGroup(cart_id=cart.id, name=name) for name in ("A", "B")]
        db.add_all(groups)
        await db.flush()
        variant = uuid4()
        lines = [
            CartLine(
                cart_id=cart.id,
                group_id=group.id,
                slot_key="storage:1",
                variant_id=variant,
                quantity=1,
            )
            for group in groups
        ]
        db.add_all(lines)
    yield owner, cart, other_market, groups, lines, variant
    async with database.sessions.begin() as db:
        await db.execute(delete(Cart).where(Cart.owner_id == owner.id))
        await db.execute(delete(Owner).where(Owner.id == owner.id))


async def test_loose_add_keeps_group_lines_and_other_market_unchanged(database, basket):
    owner, cart, other, groups, lines, variant = basket
    async with database.sessions.begin() as db:
        spare = await add_standalone(
            db,
            owner_id=owner.id,
            market="ir",
            expected_version=1,
            variant_id=variant,
            quantity=1,
        )
        spare_id = spare.id
    async with database.sessions.begin() as db:
        spare = await add_standalone(
            db,
            owner_id=owner.id,
            market="ir",
            expected_version=2,
            variant_id=variant,
            quantity=2,
        )
        assert (spare.id, spare.quantity, spare.version) == (spare_id, 3, 2)
    async with database.sessions() as db:
        current = list(await db.scalars(select(CartLine).where(CartLine.cart_id == cart.id)))
        assert len(current) == 3
        assert {line.id for line in current} == {spare_id, lines[0].id, lines[1].id}
        assert [(await db.get(CartLine, line.id)).quantity for line in lines] == [1, 1]
        assert (await db.get(Cart, cart.id)).version == 3
        assert (await db.get(Cart, other.id)).version == 1


async def test_limit_failure_does_not_write_or_advance_version(database, basket):
    owner, cart, _, _, lines, variant = basket
    with pytest.raises(ValueError, match="cart.limit"):
        async with database.sessions.begin() as db:
            await add_standalone(
                db,
                owner_id=owner.id,
                market="ir",
                expected_version=1,
                variant_id=variant,
                quantity=19,
            )
    async with database.sessions() as db:
        current = list(await db.scalars(select(CartLine).where(CartLine.cart_id == cart.id)))
        assert {entry.id for entry in current} == {entry.id for entry in lines}
        assert (await db.get(Cart, cart.id)).version == 1


async def test_configured_limits_apply_without_hidden_per_line_ceiling(database, basket):
    owner, _, _, _, _, _ = basket
    settings = Settings(max_units_per_variant=25)
    async with database.sessions.begin() as db:
        entry = await add_standalone(
            db,
            owner_id=owner.id,
            market="ir",
            expected_version=1,
            variant_id=uuid4(),
            quantity=25,
            limits=settings.limits(),
        )
        assert entry.quantity == 25
    with pytest.raises(ValueError, match="cart.limit"):
        async with database.sessions.begin() as db:
            await add_standalone(
                db,
                owner_id=owner.id,
                market="ir",
                expected_version=2,
                variant_id=uuid4(),
                quantity=1,
                limits=Limits(lines=3),
            )


async def test_foreign_owner_market_and_line_are_not_accessible(database, basket):
    owner, _, _, _, lines, _ = basket
    for actor, market in ((uuid4(), "ir"), (owner.id, "international")):
        with pytest.raises(CartNotFound):
            async with database.sessions.begin() as db:
                await change_line(
                    db,
                    owner_id=actor,
                    market=market,
                    expected_version=1,
                    line_id=lines[0].id,
                    quantity=2,
                    expected_group_version=1,
                )


async def test_group_changes_require_revision_and_keep_incomplete_group(database, basket):
    owner, cart, _, groups, lines, _ = basket
    for stale in (None, 2, True):
        with pytest.raises(CartConflict, match="group_version"):
            async with database.sessions.begin() as db:
                await change_line(
                    db,
                    owner_id=owner.id,
                    market="ir",
                    expected_version=1,
                    line_id=lines[0].id,
                    quantity=2,
                    expected_group_version=stale,
                )
    async with database.sessions.begin() as db:
        await change_line(
            db,
            owner_id=owner.id,
            market="ir",
            expected_version=1,
            line_id=lines[0].id,
            quantity=2,
            expected_group_version=1,
        )
    async with database.sessions.begin() as db:
        assert (await db.get(CartLine, lines[0].id)).version == 2
        await change_line(
            db,
            owner_id=owner.id,
            market="ir",
            expected_version=2,
            line_id=lines[0].id,
            quantity=None,
            expected_group_version=2,
        )
    async with database.sessions() as db:
        assert await db.get(CartLine, lines[0].id) is None
        remaining_group = await db.get(CartGroup, groups[0].id)
        assert (remaining_group.mode, remaining_group.version) == ("complete_build", 3)
        assert (await db.get(CartLine, lines[1].id)).quantity == 1
        assert (await db.get(Cart, cart.id)).version == 3


async def test_group_delete_is_atomic_and_does_not_remove_same_sku_spare(database, basket):
    owner, cart, _, groups, lines, variant = basket
    async with database.sessions.begin() as db:
        spare = await add_standalone(
            db,
            owner_id=owner.id,
            market="ir",
            expected_version=1,
            variant_id=variant,
            quantity=1,
        )
    async with database.sessions.begin() as db:
        await delete_group(
            db,
            owner_id=owner.id,
            market="ir",
            expected_version=2,
            group_id=groups[0].id,
            expected_group_version=1,
        )
    async with database.sessions() as db:
        assert await db.get(CartGroup, groups[0].id) is None
        assert await db.get(CartLine, lines[0].id) is None
        assert await db.get(CartLine, lines[1].id) is not None
        assert await db.get(CartLine, spare.id) is not None
        assert (await db.get(Cart, cart.id)).version == 3


async def test_concurrent_writer_waits_then_gets_version_conflict(database, basket):
    owner, cart, _, _, _, variant = basket
    loop = asyncio.get_running_loop()
    backend_pid = loop.create_future()

    async def competing_write():
        async with database.sessions.begin() as db:
            backend_pid.set_result(await db.scalar(text("SELECT pg_backend_pid()")))
            await add_standalone(
                db,
                owner_id=owner.id,
                market="ir",
                expected_version=1,
                variant_id=variant,
                quantity=1,
            )

    pending = None
    try:
        async with database.sessions.begin() as first:
            await add_standalone(
                first,
                owner_id=owner.id,
                market="ir",
                expected_version=1,
                variant_id=variant,
                quantity=1,
            )
            pending = asyncio.create_task(competing_write())
            pid = await asyncio.wait_for(backend_pid, timeout=2)
            waiting = None
            for _ in range(40):
                async with database.sessions() as observer:
                    waiting = await observer.scalar(
                        text("SELECT wait_event_type FROM pg_stat_activity WHERE pid=:pid"),
                        {"pid": pid},
                    )
                if waiting == "Lock":
                    break
                await asyncio.sleep(0.025)
            assert waiting == "Lock", "Second mutation must wait on the cart row lock"
        with pytest.raises(CartConflict) as error:
            await asyncio.wait_for(pending, timeout=3)
        assert error.value.current_version == 2
    finally:
        if pending is not None and not pending.done():
            pending.cancel()
            await asyncio.gather(pending, return_exceptions=True)
    async with database.sessions() as db:
        spare = await db.scalar(
            select(CartLine).where(CartLine.cart_id == cart.id, CartLine.group_id.is_(None))
        )
        assert spare.quantity == 1
        assert (await db.get(Cart, cart.id)).version == 2
