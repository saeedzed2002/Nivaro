import asyncio
import json
from uuid import UUID, uuid4

import httpx
import pytest
from asgi_lifespan import LifespanManager
from sqlalchemy import select

from nivaro_cart.domain.mutations import add_standalone
from nivaro_cart.infrastructure.catalog import Catalog
from nivaro_cart.infrastructure.models import Cart, CartGroup, CartLine
from nivaro_cart.main import create_app
from nivaro_cart.settings import Settings

ORIGIN = "http://127.0.0.1:8080"


@pytest.fixture
async def shop(database):
    sku = uuid4()
    state = {
        "outage": False,
        "missing": False,
        "price": 12340,
        "price_version": 1,
        "stock": 20,
        "reference": False,
        "sale": True,
        "unpriced": False,
        "hook": None,
    }

    async def catalog_transport(request):
        if state["hook"]:
            await state["hook"]()
        if state["outage"]:
            raise httpx.ConnectError("test outage", request=request)
        body = json.loads(request.content)
        items, missing = [], []
        for key in body["variant_ids"]:
            if key != str(sku) or state["missing"]:
                missing.append(key)
                continue
            offer = (
                None
                if state["unpriced"]
                else {
                    "market": body["market"],
                    "currency": body["currency"],
                    "amount_minor": state["price"] if body["market"] == "ir" else 299,
                    "price_version": state["price_version"],
                    "available_for_sale": state["sale"],
                    "reference_only": state["reference"],
                }
            )
            items.append(
                {
                    "variant_id": key,
                    "product_id": str(sku),
                    "name": "Synthetic test product",
                    "slug": "test-only",
                    "sku": "TEST",
                    "image": "/test.webp",
                    "image_kind": "illustration",
                    "available_quantity": state["stock"],
                    "offer": offer,
                }
            )
        return httpx.Response(
            200,
            json={
                "market": body["market"],
                "currency": body["currency"],
                "items": items,
                "missing_ids": missing,
                "reserves_stock": False,
            },
        )

    app = create_app(Settings(environment="test"))
    async with (
        LifespanManager(app),
        httpx.AsyncClient(
            transport=httpx.MockTransport(catalog_transport), base_url="http://catalog.test"
        ) as upstream,
    ):
        app.state.catalog = Catalog(upstream)
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url=ORIGIN, headers={"Origin": ORIGIN}
        ) as client:
            created = await client.post("/api/v1/cart/session", headers={"X-CSRF-Request": "1"})
            client.headers["X-CSRF-Token"] = created.json()["csrf_token"]
            cart = (await client.get("/api/v1/cart")).json()
            yield client, app, state, sku, cart


async def add(client, sku, version=1, quantity=1, market="ir"):
    return await client.post(
        "/api/v1/cart/items",
        json={
            "market": market,
            "expected_version": version,
            "variant_id": str(sku),
            "quantity": quantity,
        },
    )


async def test_add_reprice_and_independent_market_totals(shop):
    client, _, state, sku, cart = shop
    result = await add(client, sku, quantity=2)
    assert result.status_code == 201, result.text
    assert result.json()["version"] == 2 and result.json()["reserves_stock"] is False
    current = (await client.get("/api/v1/cart")).json()
    assert current["estimated_total_minor"] == "24680"
    assert current["lines"][0]["observed_price_minor"] == 12340
    assert current["lines"][0]["price_changed"] is False
    state["price"], state["price_version"] = 15000, 2
    changed = (await client.get("/api/v1/cart")).json()
    assert changed["estimated_total_minor"] == "30000" and changed["lines"][0]["price_changed"]
    assert changed["version"] == 2 and changed["lines"][0]["id"] == current["lines"][0]["id"]
    assert (await add(client, sku, market="international")).status_code == 201
    usd = (await client.get("/api/v1/cart?market=international")).json()
    assert (
        usd["id"] != cart["id"]
        and usd["currency"] == "USD"
        and usd["estimated_total_minor"] == "299"
    )
    assert state["stock"] == 20


async def test_outage_preserves_lines_and_allows_decrease_delete(shop):
    client, _, state, sku, _ = shop
    line = (await add(client, sku, quantity=3)).json()["line_id"]
    state["outage"] = True
    view = (await client.get("/api/v1/cart")).json()
    assert view["catalog_status"] == "unavailable" and view["estimated_total_minor"] is None
    assert view["lines"][0]["id"] == line and view["lines"][0]["status"] == "catalog_unavailable"
    assert (await add(client, sku, version=2)).status_code == 503
    decrease = await client.patch(
        f"/api/v1/cart/items/{line}", json={"market": "ir", "expected_version": 2, "quantity": 2}
    )
    assert decrease.status_code == 200 and decrease.json()["version"] == 3
    increase = await client.patch(
        f"/api/v1/cart/items/{line}", json={"market": "ir", "expected_version": 3, "quantity": 3}
    )
    assert increase.status_code == 503
    removed = await client.delete(f"/api/v1/cart/items/{line}?expected_version=3")
    assert removed.status_code == 200 and removed.json()["version"] == 4
    empty = (await client.get("/api/v1/cart")).json()
    assert empty["lines"] == [] and empty["estimated_total_minor"] == "0"


@pytest.mark.parametrize(
    "changes,status",
    [
        ({"missing": True}, "removed"),
        ({"unpriced": True}, "unpriced"),
        ({"reference": True, "sale": False}, "reference_only"),
        ({"sale": False}, "unavailable"),
        ({"stock": None}, "stock_unknown"),
        ({"stock": 0}, "insufficient_stock"),
    ],
)
async def test_unavailable_changes_are_explicit_without_losing_selection(shop, changes, status):
    client, _, state, sku, _ = shop
    assert (await add(client, sku)).status_code == 201
    state.update(changes)
    rejected = await add(client, sku, version=2)
    assert rejected.status_code == 409 and rejected.json()["error"]["code"] == f"cart.{status}"
    view = (await client.get("/api/v1/cart")).json()
    assert view["version"] == 2 and len(view["lines"]) == 1
    assert view["lines"][0]["status"] == status and view["estimated_total_minor"] is None


async def test_http_csrf_validation_and_stale_retry(shop):
    client, _, _, sku, _ = shop
    body = {"market": "ir", "expected_version": 1, "variant_id": str(sku), "quantity": 1}
    for headers in ({"X-CSRF-Token": "wrong"}, {"Origin": "https://foreign.invalid"}):
        assert (
            await client.post("/api/v1/cart/items", json=body, headers=headers)
        ).status_code == 403
    for quantity in (0, -1, True, 1.5, "2"):
        assert (
            await client.post("/api/v1/cart/items", json={**body, "quantity": quantity})
        ).status_code == 422

    async def oversized():
        yield b" " * 10000
        yield b" " * 10000

    assert (await client.post("/api/v1/cart/items", content=oversized())).status_code == 413
    assert (await add(client, sku)).status_code == 201
    retry = await add(client, sku)
    assert retry.status_code == 409 and retry.json()["error"]["current_version"] == 2
    assert (await client.get("/api/v1/cart")).json()["lines"][0]["quantity"] == 1


async def test_version_is_rechecked_after_network_without_holding_db_lock(shop, database):
    client, _, state, sku, cart_view = shop

    async def concurrent_change():
        async def change():
            async with database.sessions.begin() as db:
                cart = await db.get(Cart, UUID(cart_view["id"]))
                await add_standalone(
                    db,
                    owner_id=cart.owner_id,
                    market="ir",
                    expected_version=1,
                    variant_id=sku,
                    quantity=1,
                )

        await asyncio.wait_for(change(), timeout=2)

    state["hook"] = concurrent_change
    result = await add(client, sku)
    assert result.status_code == 409 and result.json()["error"]["current_version"] == 2
    state["hook"] = None
    view = (await client.get("/api/v1/cart")).json()
    assert len(view["lines"]) == 1 and view["lines"][0]["quantity"] == 1


async def test_stock_aggregates_groups_and_group_delete_preserves_spare(shop, database):
    client, _, state, sku, cart = shop
    async with database.sessions.begin() as db:
        group = CartGroup(cart_id=UUID(cart["id"]), name="Test build")
        db.add(group)
        await db.flush()
        component = CartLine(
            cart_id=group.cart_id,
            group_id=group.id,
            slot_key="storage:1",
            variant_id=sku,
            quantity=3,
        )
        db.add(component)
    state["stock"] = 4
    assert (await add(client, sku, quantity=2)).status_code == 409
    spare = (await add(client, sku)).json()["line_id"]
    bad_revision = await client.delete(
        f"/api/v1/cart/groups/{group.id}?expected_version=2&expected_group_version=2"
    )
    assert bad_revision.status_code == 409
    state["outage"] = True
    deleted = await client.delete(
        f"/api/v1/cart/groups/{group.id}?expected_version=2&expected_group_version=1"
    )
    assert deleted.status_code == 200
    async with database.sessions() as db:
        lines = list(await db.scalars(select(CartLine).where(CartLine.cart_id == UUID(cart["id"]))))
        assert [str(line.id) for line in lines] == [spare]
