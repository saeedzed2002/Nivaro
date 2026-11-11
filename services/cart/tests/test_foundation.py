"""Disposable PostgreSQL constraints and service readiness."""

from uuid import uuid4

import httpx
import pytest
from asgi_lifespan import LifespanManager
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.ext.asyncio import create_async_engine

from nivaro_cart.domain.limits import Limits, validate_quantities
from nivaro_cart.infrastructure.models import (
    Build,
    BuildLine,
    Cart,
    CartGroup,
    CartLine,
    Operation,
    Owner,
)
from nivaro_cart.main import app
from nivaro_cart.settings import Settings


async def test_readiness_and_private_database(database):
    async with (
        LifespanManager(app),
        httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://cart.test"
        ) as client,
    ):
        assert (await client.get("/health/ready")).status_code == 200
        assert (await client.get("/api/v1/cart")).status_code == 404
    async with database.sessions() as db:
        assert await db.scalar(text("SELECT current_database()")) == "nivaro_cart"
        assert not await db.scalar(text("SELECT rolsuper FROM pg_roles WHERE rolname=current_user"))
    for target in ("nivaro_catalog", "nivaro_identity"):
        engine = create_async_engine(Settings().database_url().set(database=target))
        try:
            with pytest.raises(OperationalError):
                async with engine.connect():
                    pass
        finally:
            await engine.dispose()


async def test_groups_keep_identical_variants_distinct_and_bound_to_cart(database):
    async with database.sessions() as db:
        owner = Owner(guest_digest=uuid4().hex * 2)
        db.add(owner)
        await db.flush()
        cart = Cart(owner_id=owner.id, market="ir", currency="IRR")
        other = Cart(owner_id=owner.id, market="international", currency="USD")
        db.add_all([cart, other])
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
        lines.append(CartLine(cart_id=cart.id, variant_id=variant, quantity=1))
        db.add_all(lines)
        await db.flush()
        assert len({line.id for line in lines}) == 3
        validate_quantities((line.variant_id, line.quantity) for line in lines)
        with pytest.raises(IntegrityError):
            async with db.begin_nested():
                db.add(
                    CartLine(
                        cart_id=other.id,
                        group_id=groups[0].id,
                        slot_key="cpu",
                        variant_id=uuid4(),
                        quantity=1,
                    )
                )
                await db.flush()
        with pytest.raises(IntegrityError):
            async with db.begin_nested():
                db.add(CartLine(cart_id=cart.id, variant_id=variant, quantity=1))
                await db.flush()
        await db.delete(groups[0])
        await db.flush()
        remaining = list(await db.scalars(select(CartLine).where(CartLine.cart_id == cart.id)))
        assert {line.id for line in remaining} == {lines[1].id, lines[2].id}
        await db.rollback()


async def test_draft_deletion_preserves_transferred_group_and_operation_uniqueness(database):
    async with database.sessions() as db:
        owner = Owner(customer_id=uuid4())
        db.add(owner)
        await db.flush()
        build = Build(owner_id=owner.id, name="A", market="ir", currency="IRR")
        cart = Cart(owner_id=owner.id, market="ir", currency="IRR")
        db.add_all([build, cart])
        await db.flush()
        db.add(BuildLine(build_id=build.id, slot_key="cpu", variant_id=uuid4(), quantity=1))
        group = CartGroup(
            cart_id=cart.id, name="A", source_build_id=build.id, source_build_version=build.version
        )
        db.add(group)
        await db.flush()
        await db.delete(build)
        await db.flush()
        assert await db.get(CartGroup, group.id) is group
        entry = dict(
            owner_id=owner.id,
            kind="transfer",
            key="request-key",
            fingerprint="a" * 64,
            result={"group_id": str(group.id)},
        )
        db.add(Operation(**entry))
        await db.flush()
        with pytest.raises(IntegrityError):
            async with db.begin_nested():
                db.add(Operation(**entry))
                await db.flush()
        await db.rollback()


@pytest.mark.parametrize("invalid", [0, -1, 21, True, 1.5])
def test_invalid_quantity(invalid):
    with pytest.raises(ValueError):
        validate_quantities([(uuid4(), invalid)])


def test_aggregate_limits_across_systems_and_spares():
    variant = uuid4()
    validate_quantities([(variant, 9), (variant, 10), (variant, 1)])
    with pytest.raises(ValueError, match="cart.limit"):
        validate_quantities([(variant, 10), (variant, 10), (variant, 1)])
    with pytest.raises(ValueError, match="cart.limit"):
        validate_quantities([(uuid4(), 1) for _ in range(51)])
    with pytest.raises(ValueError, match="cart.limit"):
        validate_quantities([(uuid4(), 1), (uuid4(), 1)], Limits(lines=1))
