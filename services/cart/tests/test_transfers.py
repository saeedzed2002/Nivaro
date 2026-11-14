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


async def test_comparison_preserves_both_drafts_and_unknown_prices(transfer):
    client, path, state, variant, draft = transfer
    duplicate = await client.post(
        f"{path}/duplicate", json={"name": "Build B", "expected_version": 1}
    )
    other = duplicate.json()["id"]
    changed = {
        **draft,
        "name": "Build B",
        "expected_version": 1,
        "selections": [
            {"slot_key": "storage:1", "variant_id": str(variant), "quantity": 1},
            {"slot_key": "monitor", "variant_id": str(uuid4())},
        ],
    }
    assert (await client.patch(f"/api/v1/builds/{other}", json=changed)).status_code == 200
    url = f"{path}/comparison?other_id={other}"
    comparison = await client.get(url)
    assert comparison.status_code == 200, comparison.text
    result = comparison.json()
    assert result["currency"] == "IRR" and result["reserves_stock"] is False
    assert result["left"]["build"]["version"] == 1 and result["right"]["build"]["version"] == 2
    assert result["left"]["known_components_minor"] == "24680"
    assert result["left"]["known_peripherals_minor"] is None
    assert result["right"]["known_components_minor"] == "12340"
    assert result["right"]["known_peripherals_minor"] == "12340"
    assert result["left"]["evaluation"]["status"] == "incomplete"
    rows = {row["slot_key"]: row for row in result["slots"]}
    assert rows["monitor"]["left"] is None and rows["monitor"]["different"]
    assert rows["storage:1"]["different"]
    state["unpriced"] = True
    result = (await client.get(url)).json()
    assert result["right"]["known_components_minor"] is None
    assert result["right"]["known_peripherals_minor"] is None
    assert result["right"]["unpriced_slots"] == ["monitor", "storage:1"]
    assert (await client.get(path)).json()["version"] == 1
    assert (await client.get(f"/api/v1/builds/{other}")).json()["version"] == 2


async def test_comparison_rejects_cross_market_and_foreign_drafts(transfer):
    client, path, _, _, draft = transfer
    overseas = await client.post("/api/v1/builds", json={**draft, "market": "international"})
    assert overseas.status_code == 201
    rejected = await client.get(f"{path}/comparison", params={"other_id": overseas.json()["id"]})
    assert (
        rejected.status_code == 422
        and rejected.json()["error"]["code"] == "build.comparison_market_mismatch"
    )
    assert (
        await client.get(f"{path}/comparison", params={"other_id": path.rsplit("/", 1)[1]})
    ).status_code == 422
    assert (
        await client.get(f"{path}/comparison", params={"other_id": str(uuid4())})
    ).status_code == 404


async def transferred_group(client, path):
    _, body = await reviewed(client, path)
    created = await client.post(f"{path}/cart-transfers", json=body)
    assert created.status_code == 201, created.text
    return created.json()


async def test_group_edit_retains_slot_identity_and_does_not_change_draft_or_other_system(transfer):
    client, path, state, variant, draft = transfer
    first = await transferred_group(client, path)
    _, next_body = await reviewed(client, path)
    second = (
        await client.post(
            f"{path}/cart-transfers", json=next_body, headers={"Idempotency-Key": "second"}
        )
    ).json()
    basket = (await client.get("/api/v1/cart")).json()
    first_line = next(line for line in basket["lines"] if line["group_id"] == first["group_id"])
    second_line = next(line for line in basket["lines"] if line["group_id"] == second["group_id"])
    url = f"/api/v1/cart/groups/{first['group_id']}"
    state["stock"] = 5
    proposed = {
        **draft,
        "name": "Edited system",
        "market": "ir",
        "expected_version": 3,
        "expected_group_version": 1,
        "selections": [{"slot_key": "storage:1", "variant_id": str(variant), "quantity": 3}],
    }
    review = await client.post(f"{url}/review", json=proposed)
    assert review.status_code == 200 and review.json()["blocker"] is None, review.text
    receipt = await client.patch(
        url, json={**proposed, "review_digest": review.json()["review_digest"]}
    )
    assert receipt.status_code == 200, receipt.text
    assert receipt.json()["version"] == 4 and receipt.json()["group"]["version"] == 2
    current = {line["id"]: line for line in (await client.get("/api/v1/cart")).json()["lines"]}
    assert current[first_line["id"]]["quantity"] == 3 and current[first_line["id"]]["version"] == 2
    assert (
        current[second_line["id"]]["quantity"] == 2 and current[second_line["id"]]["version"] == 1
    )
    assert (await client.get(path)).json()["selections"][0]["quantity"] == 2


async def test_group_edit_rejects_new_prices_and_loses_a_version_race_atomically(transfer):
    client, path, state, _, draft = transfer
    first = await transferred_group(client, path)
    url = f"/api/v1/cart/groups/{first['group_id']}"
    proposed = {
        **draft,
        "name": "Edited",
        "market": "ir",
        "expected_version": 2,
        "expected_group_version": 1,
        "selections": [
            {**draft["selections"][0], "quantity": 3},
            {"slot_key": "storage:2", "variant_id": str(uuid4())},
        ],
    }
    review = (await client.post(f"{url}/review", json=proposed)).json()
    assert review["review_digest"]
    state["amount"], state["version"] = 15000, 2
    stale = await client.patch(url, json={**proposed, "review_digest": review["review_digest"]})
    assert stale.status_code == 409 and stale.json()["error"]["code"] == "build.review_changed"
    assert len((await client.get("/api/v1/cart")).json()["lines"]) == 1
    latest = (await client.post(f"{url}/review", json=proposed)).json()
    confirmed = {**proposed, "review_digest": latest["review_digest"]}
    one, two = await asyncio.gather(
        client.patch(url, json=confirmed), client.patch(url, json=confirmed)
    )
    assert sorted([one.status_code, two.status_code]) == [200, 409]
    cart = (await client.get("/api/v1/cart")).json()
    assert cart["version"] == 3 and len(cart["lines"]) == 2
    assert all(line["observed_price_minor"] == 15000 for line in cart["lines"])
    bad = await client.post(f"{url}/review", json={**proposed, "expected_version": 3})
    assert bad.status_code == 409 and bad.json()["error"]["code"] == "cart.group_version_conflict"
    missing = await client.post(
        f"/api/v1/cart/groups/{uuid4()}/review", json={**proposed, "expected_version": 3}
    )
    assert missing.status_code == 404
