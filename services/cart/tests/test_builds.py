import asyncio
from uuid import uuid4

import httpx
import pytest
from asgi_lifespan import LifespanManager

from nivaro_cart.main import create_app
from nivaro_cart.settings import Settings

ORIGIN = "http://127.0.0.1:8080"
BUILDS = "/api/v1/builds"


async def start_guest(client):
    result = await client.post("/api/v1/cart/session", headers={"X-CSRF-Request": "1"})
    assert result.status_code == 200
    client.headers["X-CSRF-Token"] = result.json()["csrf_token"]


@pytest.fixture
async def builds(database):
    app = create_app(Settings(environment="test"))
    async with (
        LifespanManager(app),
        httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url=ORIGIN, headers={"Origin": ORIGIN}
        ) as client,
    ):
        await start_guest(client)
        yield client, app


def content(name="Build A"):
    return {
        "name": name,
        "mode": "parts_only",
        "requires_dedicated_gpu": True,
        "selections": [
            {"slot_key": "storage:1", "variant_id": str(uuid4()), "quantity": 2},
            {"slot_key": "cpu", "variant_id": str(uuid4())},
        ],
    }


async def test_saved_build_copy_and_edit_are_independent_across_reload(builds):
    client, _ = builds
    body = content()
    response = await client.post(BUILDS, json={**body, "market": "international"})
    assert response.status_code == 201, response.text
    original = response.json()
    assert original["currency"] == "USD" and original["reserves_stock"] is False
    original_path = f"{BUILDS}/{original['id']}"
    response = await client.post(
        f"{original_path}/duplicate", json={"name": "Build B", "expected_version": 1}
    )
    assert response.status_code == 201, response.text
    duplicate = response.json()
    assert duplicate["id"] != original["id"]
    assert duplicate["mode"] == "parts_only" and duplicate["requires_dedicated_gpu"] is True
    assert {item["variant_id"] for item in duplicate["selections"]} == {
        item["variant_id"] for item in original["selections"]
    }
    duplicate_path = f"{BUILDS}/{duplicate['id']}"
    edit = content("Variant B")
    edit["selections"].pop()
    edited = await client.patch(duplicate_path, json={**edit, "expected_version": 1})
    assert edited.status_code == 200 and edited.json()["version"] == 2
    assert (await client.get(duplicate_path)).json()["selections"] == edit["selections"]
    restored = (await client.get(original_path)).json()
    assert restored["version"] == 1 and len(restored["selections"]) == 2
    assert len((await client.get(BUILDS, params={"market": "international"})).json()) == 2
    assert (await client.get(BUILDS, params={"market": "ir"})).json() == []
    first = (await client.get(BUILDS, params={"market": "international", "limit": 1})).json()
    second = (
        await client.get(
            BUILDS, params={"market": "international", "limit": 1, "after": first[0]["id"]}
        )
    ).json()
    assert len(second) == 1 and first[0]["id"] != second[0]["id"]
    assert (await client.delete(f"{duplicate_path}?expected_version=1")).status_code == 409
    assert (await client.delete(f"{duplicate_path}?expected_version=2")).status_code == 204
    assert (await client.get(duplicate_path)).status_code == 404
    assert (await client.get(original_path)).status_code == 200


async def test_builds_require_ownership_csrf_valid_slots_and_explicit_market(builds):
    client, app = builds
    body = {**content(), "market": "ir"}
    good = await client.post(BUILDS, json=body)
    path = f"{BUILDS}/{good.json()['id']}"
    for selections in (
        [body["selections"][0]] * 2,
        [body["selections"][1], {**body["selections"][1], "slot_key": "cpu:2"}],
        [{**body["selections"][1], "quantity": 2}],
        [{**body["selections"][0], "slot_key": "unknown:1"}],
    ):
        assert (
            await client.post(BUILDS, json={**body, "selections": selections})
        ).status_code == 422
    assert (
        await client.post(BUILDS, json=body, headers={"X-CSRF-Token": "wrong"})
    ).status_code == 403
    assert (await client.patch(path, json={**body, "expected_version": 1})).status_code == 422
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url=ORIGIN, headers={"Origin": ORIGIN}
    ) as other:
        await start_guest(other)
        assert (await other.get(path)).status_code == 404
        assert (await other.get(BUILDS, params={"market": "ir"})).json() == []
        assert (
            await other.post(f"{path}/duplicate", json={"name": "Copy", "expected_version": 1})
        ).status_code == 404
        assert (await other.delete(f"{path}?expected_version=1")).status_code == 404


async def test_build_concurrent_replacements_require_matching_revision(builds):
    client, _ = builds
    created = (await client.post(BUILDS, json={**content(), "market": "ir"})).json()
    path = f"{BUILDS}/{created['id']}"
    a, b = await asyncio.gather(
        client.patch(path, json={**content("First"), "expected_version": 1}),
        client.patch(path, json={**content("Second"), "expected_version": 1}),
    )
    assert sorted([a.status_code, b.status_code]) == [200, 409]
    winner, failed = (a, b) if a.status_code == 200 else (b, a)
    assert failed.json()["error"] == {"code": "build.version_conflict", "current_version": 2}
    saved = (await client.get(path)).json()
    assert saved["name"] == winner.json()["name"] and saved["version"] == 2
