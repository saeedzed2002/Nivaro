import asyncio
from uuid import UUID, uuid4

import httpx
import pytest
from asgi_lifespan import LifespanManager
from sqlalchemy import select

from nivaro_cart.api.authorization import CustomerPrincipal
from nivaro_cart.domain.errors import AuthorizationError
from nivaro_cart.domain.ownership import GUEST_COOKIE, issue_guest, owned_cart
from nivaro_cart.infrastructure.models import Cart, CartGroup, CartLine, Operation
from nivaro_cart.main import create_app
from nivaro_cart.settings import Settings

ORIGIN = "http://127.0.0.1:8080"
PATH = "/api/v1/cart/merge"
COOKIE = "nivaro_customer_access"


@pytest.fixture
async def merge_setup(database):
    app = create_app(Settings(environment="test"))
    customer_id = uuid4()
    session_id = uuid4()
    component_id = uuid4()
    async with database.sessions.begin() as db:
        guest = await issue_guest(db)
        source = await owned_cart(db, guest.owner, "ir")
        overseas = await owned_cart(db, guest.owner, "international")
        groups = [CartGroup(cart_id=source.id, name="Same build") for _ in range(2)]
        db.add_all(groups)
        await db.flush()
        children = [
            CartLine(
                cart_id=source.id,
                group_id=group.id,
                slot_key="storage:1",
                variant_id=component_id,
                quantity=1,
            )
            for group in groups
        ]
        spare = CartLine(cart_id=source.id, variant_id=component_id, quantity=2)
        other = CartLine(cart_id=overseas.id, variant_id=component_id, quantity=4)
        db.add_all([*children, spare, other])
        await db.flush()

    class Identity:
        async def check(self, access, *, mutating, origin, csrf):
            if access != "verified-customer":
                raise AuthorizationError("auth.required", 401)
            if mutating and csrf != "customer-csrf":
                raise AuthorizationError("auth.forbidden", 403)
            return CustomerPrincipal(
                user_id=customer_id, session_id=session_id, kind="customer", permissions=[]
            )

    class NoCatalog:
        async def summaries(self, ids, market):
            return dict.fromkeys(ids)

    async with (
        LifespanManager(app),
        httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url=ORIGIN,
            headers={
                "Origin": ORIGIN,
                "X-CSRF-Token": "customer-csrf",
                "Idempotency-Key": "first-merge",
            },
        ) as client,
    ):
        app.state.authorization = Identity()
        app.state.catalog = NoCatalog()
        client.cookies.set(COOKIE, "verified-customer")
        client.cookies.set(GUEST_COOKIE, guest.cookie)
        target = (await client.get("/api/v1/cart")).json()
        payload = {
            "market": "ir",
            "guest_cart_id": str(source.id),
            "expected_guest_version": source.version,
            "expected_version": target["version"],
        }
        yield client, payload, UUID(target["id"]), source, overseas, groups, children, spare, other


async def test_merge_preserves_group_and_line_ids_and_only_combines_standalones(
    merge_setup, database
):
    client, payload, target, source, overseas, groups, children, spare, other = merge_setup
    async with database.sessions.begin() as db:
        existing = CartLine(cart_id=target, variant_id=spare.variant_id, quantity=3)
        db.add(existing)
    preview = await client.get(PATH, params={"market": "ir"})
    assert preview.json() == {
        "cart_id": str(source.id),
        "version": 1,
        "line_count": 3,
        "group_count": 2,
    }
    merged = await client.post(PATH, json=payload)
    assert merged.status_code == 200, merged.text
    assert merged.json() == {
        "cart_id": str(target),
        "version": 2,
        "guest_version": 2,
        "moved_groups": 2,
        "moved_lines": 2,
        "combined_lines": 1,
        "reserves_stock": False,
    }
    assert (await client.post(PATH, json=payload)).json() == merged.json()
    assert (await client.get(PATH, params={"market": "ir"})).json() is None
    assert (await client.get(PATH, params={"market": "international"})).json()["cart_id"] == str(
        overseas.id
    )
    async with database.sessions() as db:
        for group, child in zip(groups, children, strict=True):
            row = await db.get(CartLine, child.id)
            assert row.group_id == group.id and row.cart_id == target
            assert (await db.get(CartGroup, group.id)).cart_id == target
        assert (await db.get(CartLine, existing.id)).quantity == 5
        assert (await db.get(CartLine, existing.id)).version == 2
        assert await db.get(CartLine, spare.id) is None
        assert (await db.get(CartLine, other.id)).cart_id == overseas.id
    client.cookies.delete(COOKIE)
    assert (await client.get("/api/v1/cart")).json()["lines"] == []


async def test_two_tabs_with_different_keys_cannot_repeat_the_merge(merge_setup, database):
    client, payload, target, _, _, _, children, spare, _ = merge_setup
    first, second = await asyncio.gather(
        client.post(PATH, json=payload),
        client.post(PATH, json=payload, headers={"Idempotency-Key": "second-merge"}),
    )
    assert sorted([first.status_code, second.status_code]) == [200, 409]
    conflict = first if first.status_code == 409 else second
    assert conflict.json()["error"] == {"code": "cart.guest_version_conflict", "current_version": 2}
    success_key = "second-merge" if first.status_code == 409 else "first-merge"
    changed = await client.post(
        PATH,
        json={**payload, "expected_guest_version": 2},
        headers={"Idempotency-Key": success_key},
    )
    assert (
        changed.status_code == 409
        and changed.json()["error"]["code"] == "cart.idempotency_conflict"
    )
    async with database.sessions() as db:
        lines = list(await db.scalars(select(CartLine).where(CartLine.cart_id == target)))
        assert {line.id for line in lines} == {*(line.id for line in children), spare.id}
        assert sum(line.quantity for line in lines) == 4


async def test_limit_and_ownership_conflicts_leave_source_intact(merge_setup, database):
    client, payload, target, source, _, groups, children, spare, _ = merge_setup
    async with database.sessions.begin() as db:
        db.add(CartLine(cart_id=target, variant_id=spare.variant_id, quantity=18))
    for update, header, expected in (
        ({}, {"X-CSRF-Token": "wrong"}, 403),
        ({"guest_cart_id": str(uuid4())}, {}, 404),
        ({"market": "international"}, {}, 404),
        ({"expected_version": 2}, {}, 409),
        ({}, {}, 409),
    ):
        result = await client.post(PATH, json={**payload, **update}, headers=header)
        assert result.status_code == expected, result.text
    assert result.json()["error"]["code"] == "cart.limit"
    async with database.sessions() as db:
        lines = list(await db.scalars(select(CartLine).where(CartLine.cart_id == source.id)))
        assert {line.id for line in lines} == {*(line.id for line in children), spare.id}
        assert (await db.get(Cart, source.id)).version == 1
        assert (await db.get(Cart, target)).version == 1
        assert set(
            await db.scalars(select(CartGroup.id).where(CartGroup.cart_id == source.id))
        ) == {group.id for group in groups}
        owner = (await db.get(Cart, target)).owner_id
        assert await db.scalar(select(Operation).where(Operation.owner_id == owner)) is None
    client.cookies.delete(GUEST_COOKIE)
    assert (await client.get(PATH, params={"market": "ir"})).json() is None
    assert (await client.post(PATH, json=payload)).status_code == 401
