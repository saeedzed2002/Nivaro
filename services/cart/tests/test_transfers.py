import asyncio
from uuid import uuid4

import httpx
import pytest
from asgi_lifespan import LifespanManager

from nivaro_cart.infrastructure.catalog import (
    CatalogUnavailable,
    Evaluation,
    Offer,
    SelectionUnavailable,
    Summary,
)
from nivaro_cart.main import create_app
from nivaro_cart.settings import Settings

ORIGIN = "http://127.0.0.1:8080"


@pytest.fixture
async def transfer(database):
    app = create_app(Settings(environment="test"))
    variant = uuid4()
    state = {
        "amount": 12340,
        "version": 1,
        "spec": 1,
        "stock": 20,
        "status": "incomplete",
        "missing": False,
        "unpriced": False,
        "outage": False,
        "hook": None,
        "role_error": False,
    }

    class Catalog:
        async def summaries(self, ids, market):
            return {
                key: None
                if state["missing"]
                else Summary(
                    variant_id=key,
                    product_id=variant,
                    name="Synthetic SSD",
                    sku="TEST",
                    slug="test",
                    image="/test.webp",
                    image_kind="illustration",
                    available_quantity=state["stock"],
                    offer=None
                    if state["unpriced"]
                    else Offer(
                        market=market,
                        currency="IRR",
                        amount_minor=state["amount"],
                        price_version=state["version"],
                        available_for_sale=True,
                        reference_only=False,
                    ),
                )
                for key in ids
            }

        async def evaluate(self, *, market, mode, dedicated_gpu, selections):
            if state["outage"]:
                raise CatalogUnavailable
            if state["role_error"]:
                raise SelectionUnavailable
            if state["hook"]:
                await state["hook"]()
            return Evaluation(
                market=market,
                currency="IRR",
                mode=mode,
                selection_hash="a" * 64,
                spec_versions={key: state["spec"] for _, key, _ in selections},
                ruleset_version="test-v1",
                status=state["status"],
                findings=[],
                evaluated_at="2026-11-14T00:00:00Z",
                estimated_power_w=None,
                power_method="test",
                reserves_stock=False,
            )

    async with (
        LifespanManager(app),
        httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url=ORIGIN,
            headers={"Origin": ORIGIN, "Idempotency-Key": "transfer-1"},
        ) as client,
    ):
        app.state.catalog = Catalog()
        session = await client.post("/api/v1/cart/session", headers={"X-CSRF-Request": "1"})
        client.headers["X-CSRF-Token"] = session.json()["csrf_token"]
        draft = {
            "name": "Test PC",
            "mode": "parts_only",
            "requires_dedicated_gpu": True,
            "selections": [{"slot_key": "storage:1", "variant_id": str(variant), "quantity": 2}],
        }
        created = await client.post("/api/v1/builds", json={**draft, "market": "ir"})
        assert created.status_code == 201, created.text
        path = f"/api/v1/builds/{created.json()['id']}"
        yield client, path, state, variant, draft


async def reviewed(client, path):
    response = await client.get(f"{path}/review")
    assert response.status_code == 200, response.text
    report = response.json()
    return report, {
        "expected_build_version": report["build"]["version"],
        "expected_cart_version": report["cart_version"],
        "review_digest": report["review_digest"],
    }


async def test_concurrent_transfer_replays_same_group_even_after_draft_deletion(transfer):
    client, path, state, variant, _ = transfer
    report, body = await reviewed(client, path)
    assert report["evaluation"]["status"] == "incomplete" and report["blocker"] is None
    url = f"{path}/cart-transfers"
    a, b = await asyncio.gather(client.post(url, json=body), client.post(url, json=body))
    assert a.status_code == b.status_code == 201, (a.text, b.text)
    assert a.json() == b.json()
    second_review, next_body = await reviewed(client, path)
    assert second_review["cart_version"] == 2
    second = await client.post(url, json=next_body, headers={"Idempotency-Key": "transfer-2"})
    assert second.status_code == 201 and second.json()["group_id"] != a.json()["group_id"]
    assert (await client.delete(f"{path}?expected_version=1")).status_code == 204
    state["outage"] = True
    assert (await client.post(url, json=body)).json() == a.json()
    changed = await client.post(url, json={**body, "review_digest": "b" * 64})
    assert (
        changed.status_code == 409
        and changed.json()["error"]["code"] == "cart.idempotency_conflict"
    )
    basket = (await client.get("/api/v1/cart")).json()
    assert len(basket["groups"]) == 2 and all(
        group["requires_dedicated_gpu"] and group["mode"] == "parts_only"
        for group in basket["groups"]
    )
    assert {line["variant_id"] for line in basket["lines"]} == {str(variant)}
    assert len({line["id"] for line in basket["lines"]}) == 2
    assert sum(line["quantity"] for line in basket["lines"]) == 4


@pytest.mark.parametrize(
    ("changes", "code"),
    [
        ({"amount": 13000, "version": 2}, "build.review_changed"),
        ({"spec": 2}, "build.review_changed"),
        ({"stock": 1}, "build.items_unavailable"),
        ({"unpriced": True}, "build.items_unavailable"),
        ({"missing": True}, "build.items_unavailable"),
        ({"role_error": True}, "build.selection_unavailable"),
        ({"outage": True}, "catalog.unavailable"),
    ],
)
async def test_transfer_rejects_stale_or_unavailable_review_without_partial_group(
    transfer, changes, code
):
    client, path, state, _, _ = transfer
    _, body = await reviewed(client, path)
    state.update(changes)
    result = await client.post(f"{path}/cart-transfers", json=body)
    assert result.status_code == (503 if code == "catalog.unavailable" else 409), result.text
    assert result.json()["error"]["code"] == code
    cart = (await client.get("/api/v1/cart")).json()
    assert cart["groups"] == [] and cart["lines"] == [] and cart["version"] == 1


async def test_full_build_blocks_while_unverified_and_cart_stock_is_aggregated(transfer):
    client, path, state, variant, draft = transfer
    assert (
        await client.patch(path, json={**draft, "mode": "complete_build", "expected_version": 1})
    ).status_code == 200
    report, body = await reviewed(client, path)
    assert report["review_digest"] is None and report["blocker"] == "build.compatibility_required"
    blocked = await client.post(f"{path}/cart-transfers", json={**body, "review_digest": "b" * 64})
    assert (
        blocked.status_code == 409
        and blocked.json()["error"]["code"] == "build.compatibility_required"
    )
    state["status"], state["stock"] = "compatible", 3
    add = await client.post(
        "/api/v1/cart/items",
        json={"market": "ir", "expected_version": 1, "variant_id": str(variant), "quantity": 2},
    )
    assert add.status_code == 201
    report, _ = await reviewed(client, path)
    assert (
        report["blocker"] == "build.items_unavailable"
        and report["lines"][0]["status"] == "insufficient_stock"
    )


async def test_transfer_rechecks_draft_after_catalog_io(transfer):
    client, path, state, _, draft = transfer
    _, body = await reviewed(client, path)

    async def concurrent_edit():
        result = await asyncio.wait_for(
            client.patch(path, json={**draft, "name": "Changed", "expected_version": 1}), timeout=3
        )
        assert result.status_code == 200

    state["hook"] = concurrent_edit
    response = await client.post(f"{path}/cart-transfers", json=body)
    assert response.status_code == 409 and response.json()["error"] == {
        "code": "build.version_conflict",
        "current_version": 2,
    }
    assert (await client.get("/api/v1/cart")).json()["groups"] == []
