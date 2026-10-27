"""Real PostgreSQL checks; run only with explicitly configured CATALOG_DB_HOST.

The seed is prepared separately. Each test runs in a rolled-back transaction and
overrides the API session dependency, so it cannot persist fixture mutations.
"""

import os
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import func, select, text, update
from sqlalchemy.exc import IntegrityError

from nivaro_catalog.infrastructure.database import Database
from nivaro_catalog.infrastructure.models import CategoryRow, OfferRow, ProductRow, VariantRow
from nivaro_catalog.infrastructure.seed import seed
from nivaro_catalog.main import app
from nivaro_catalog.main import session as session_dependency
from nivaro_catalog.settings import Settings

pytestmark = pytest.mark.skipif(
    not os.getenv("CATALOG_DB_HOST"), reason="Explicit catalog test database configuration required"
)


@pytest.fixture
async def api():
    database = Database(Settings())
    async with database.engine.connect() as connection:
        transaction = await connection.begin()
        from sqlalchemy.ext.asyncio import AsyncSession

        async with AsyncSession(bind=connection) as session:

            async def override():
                yield session

            app.dependency_overrides[session_dependency] = override
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://catalog.test"
            ) as client:
                yield client, session
            app.dependency_overrides.clear()
        if transaction.is_active:
            await transaction.rollback()
    await database.engine.dispose()


async def test_readiness_and_seed_repeatability(api):
    client, session = api
    assert (await client.get("/health/ready")).status_code == 200
    before = await session.scalar(select(func.count()).select_from(ProductRow))
    await session.run_sync(seed)
    await session.run_sync(seed)
    assert await session.scalar(select(func.count()).select_from(ProductRow)) == before == 12
    assert await session.scalar(select(func.count()).select_from(VariantRow)) == 13


async def test_restricted_database_role(api):
    _, session = api
    role = (
        await session.execute(
            text(
                "SELECT rolsuper, rolcreatedb, rolcreaterole, rolreplication FROM pg_roles WHERE rolname = current_user"
            )
        )
    ).one()
    assert tuple(role) == (False, False, False, False)
    assert await session.scalar(text("SELECT current_database()")) == "nivaro_catalog"


async def test_api_search_filter_pagination_and_request_id(api):
    client, _ = api
    response = await client.get(
        "/api/v1/catalog/products?q=كيبو&page_size=1", headers={"X-Request-ID": "safe-id"}
    )
    assert response.status_code == 200 and response.headers["X-Request-ID"] == "safe-id"
    body = response.json()
    assert body["total"] == 1 and body["items"][0]["category"] == "keyboard"
    assert (await client.get("/api/v1/catalog/products?category=cpu")).json()["total"] == 2
    assert (await client.get("/api/v1/catalog/products?in_stock=true")).json()["total"] == 0
    assert (await client.get("/api/v1/catalog/products?q=%25")).json()["total"] == 0
    first = (await client.get("/api/v1/catalog/products?page_size=2&page=1&sort=name")).json()[
        "items"
    ]
    second = (await client.get("/api/v1/catalog/products?page_size=2&page=2&sort=name")).json()[
        "items"
    ]
    assert len(first) == len(second) == 2
    assert not {p["id"] for p in first} & {p["id"] for p in second}


async def test_missing_and_validation_errors_are_structured(api):
    client, _ = api
    assert (await client.get("/api/v1/catalog/products/missing")).json()["error"][
        "code"
    ] == "catalog.not_found"
    for query in ("page_size=101", "sort=rating", "min_price=100&max_price=10", "market=invalid"):
        response = await client.get("/api/v1/catalog/products?" + query)
        assert response.status_code == 422
        assert response.json()["error"]["request_id"]


async def test_packaging_prices_and_missing_prices_remain_independent(api):
    client, _ = api
    response = await client.get("/api/v1/catalog/products/amd-ryzen-7-9800x3d")
    variants = response.json()["variants"]
    assert len(variants) == 2
    offers = {v["packaging"]["en"]: v["offers"] for v in variants}
    assert (
        offers["tray"][0]["currency"] == "IRR" and offers["tray"][0]["amount_minor"] == 1133900000
    )
    assert offers["boxed"][0]["currency"] == "USD" and offers["boxed"][0]["amount_minor"] == 46900
    assert all(not o["available_for_sale"] for v in variants for o in v["offers"])
    missing = (await client.get("/api/v1/catalog/products/amd-ryzen-7-9700x")).json()
    assert missing["variants"][0]["offers"] == []
    assert missing["variants"][0]["specifications"]["max_package_power_w"] is None


async def test_database_change_is_visible_and_drafts_are_hidden(api):
    client, session = api
    await session.execute(
        update(ProductRow)
        .where(ProductRow.slug == "amd-ryzen-7-9700x")
        .values(name="TEST changed name")
    )
    assert (await client.get("/api/v1/catalog/products/amd-ryzen-7-9700x")).json()[
        "name"
    ] == "TEST changed name"
    await session.execute(
        update(ProductRow).where(ProductRow.slug == "amd-ryzen-7-9700x").values(status="draft")
    )
    assert (await client.get("/api/v1/catalog/products/amd-ryzen-7-9700x")).status_code == 404
    assert (await client.get("/api/v1/catalog/products")).json()["total"] == 11


async def test_documented_core_build_is_selectable_but_not_falsely_certified(api):
    client, _ = api
    products = (await client.get("/api/v1/catalog/products?page_size=100")).json()["items"]
    selections = []
    for role in ("cpu", "motherboard", "memory", "storage", "case", "psu", "cooler"):
        product = next(item for item in products if item["category"] == role)
        variant = product["variants"][0]
        assert variant["evidence"]
        selections.append({"slot_key": role, "role": role, "variant_id": variant["id"]})
    response = await client.post(
        "/api/v1/catalog/build-evaluations",
        json={
            "market": "ir",
            "currency": "IRR",
            "selections": selections,
        },
    )
    assert response.status_code == 200
    assert response.json()["status"] == "needs_review"
    assert len(response.json()["unpriced_slots"]) >= 6


async def test_product_comparison_and_same_category_guard(api):
    client, _ = api
    products = (await client.get("/api/v1/catalog/products")).json()["items"]
    cpu_ids = [p["variants"][0]["id"] for p in products if p["category"] == "cpu"]
    response = await client.post(
        "/api/v1/catalog/comparisons",
        json={"market": "international", "currency": "USD", "variant_ids": cpu_ids},
    )
    assert response.status_code == 200, response.text
    comparison = response.json()
    assert comparison["declares_winner"] is False
    assert any(r["key"] == "tdp_w" and r["different"] for r in comparison["rows"])
    assert any(
        r["key"] == "max_package_power_w" and r["values"] == [None, None]
        for r in comparison["rows"]
    )
    keyboard = next(p["variants"][0]["id"] for p in products if p["category"] == "keyboard")
    response = await client.post(
        "/api/v1/catalog/comparisons",
        json={"market": "ir", "currency": "IRR", "variant_ids": [cpu_ids[0], keyboard]},
    )
    assert response.status_code == 422


async def test_evaluation_from_real_catalog_is_incomplete_not_fake_green(api):
    client, _ = api
    product = (await client.get("/api/v1/catalog/products/amd-ryzen-7-9800x3d")).json()
    variant = next(v for v in product["variants"] if v["packaging"]["en"] == "tray")
    body = {
        "market": "ir",
        "currency": "IRR",
        "selections": [
            {"slot_key": "cpu", "role": "cpu", "variant_id": variant["id"], "quantity": 1}
        ],
    }
    response = await client.post("/api/v1/catalog/build-evaluations", json=body)
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["status"] == "incomplete" and result["component_subtotal_minor"] == 1133900000
    assert result["estimated_power_w"] is None and result["reserves_stock"] is False
    body["previous"] = {
        key: result[key] for key in ("selection_hash", "spec_versions", "ruleset_version")
    }
    body["previous"]["ruleset_version"] = "old-rules"
    assert (await client.post("/api/v1/catalog/build-evaluations", json=body)).json()[
        "stale_reasons"
    ] == ["rules_changed"]


@pytest.mark.parametrize(
    "table,values",
    [
        (VariantRow, {"on_hand": -1}),
        (VariantRow, {"reserved": 1}),
        (OfferRow, {"amount_minor": -10}),
        (OfferRow, {"available_for_sale": True}),
    ],
)
async def test_database_constraints_reject_invalid_mutations(api, table, values):
    _, session = api
    identifier = await session.scalar(select(table.id).limit(1))
    with pytest.raises(IntegrityError), session.no_autoflush:
        async with session.begin_nested():
            await session.execute(update(table).where(table.id == identifier).values(**values))


async def test_category_depth_enforced_by_postgres(api):
    _, session = api
    parent = await session.scalar(
        select(CategoryRow.id).where(CategoryRow.parent_id.is_(None)).limit(1)
    )
    child = uuid4()
    session.add(
        CategoryRow(
            id=child,
            slug="test-child",
            name={"fa": "آزمون", "en": "Test"},
            image="cpu",
            parent_id=parent,
        )
    )
    await session.flush()
    with pytest.raises(IntegrityError):
        async with session.begin_nested():
            session.add(
                CategoryRow(
                    id=uuid4(),
                    slug="test-grandchild",
                    name={"fa": "آزمون", "en": "Test"},
                    image="cpu",
                    parent_id=child,
                )
            )
            await session.flush()


async def test_unversioned_specs_and_price_edits_are_rejected(api):
    client, session = api
    product = (await client.get("/api/v1/catalog/products/amd-ryzen-7-9800x3d")).json()
    variant = product["variants"][0]
    identifier = variant["id"]
    altered = variant["specifications"] | {"tdp_w": 121}
    with pytest.raises(IntegrityError):
        async with session.begin_nested():
            await session.execute(
                update(VariantRow).where(VariantRow.id == identifier).values(specifications=altered)
            )
    await session.execute(
        update(VariantRow)
        .where(VariantRow.id == identifier)
        .values(specifications=altered, spec_version=variant["spec_version"] + 1)
    )
    fresh = (await client.get("/api/v1/catalog/variants/" + identifier)).json()
    assert fresh["spec_version"] == variant["spec_version"] + 1
    assert fresh["specifications"]["tdp_w"] == 121
    offer = await session.scalar(select(OfferRow).limit(1))
    with pytest.raises(IntegrityError):
        async with session.begin_nested():
            await session.execute(
                update(OfferRow)
                .where(OfferRow.id == offer.id)
                .values(amount_minor=offer.amount_minor + 10)
            )


async def test_bounded_chunked_body_is_rejected_before_parsing(api):
    client, _ = api

    async def chunks():
        for _ in range(5):
            yield b"x" * 16384

    response = await client.post("/api/v1/catalog/build-evaluations", content=chunks())
    assert response.status_code == 413
    assert response.json()["error"]["code"] == "request.too_large"
    assert response.headers["X-Request-ID"] == response.json()["error"]["request_id"]


async def test_internal_docs_and_unknown_routes_are_not_exposed(api):
    client, _ = api
    for path in ("/docs", "/openapi.json", "/internal/test", "/api/v1/catalog/not-a-route"):
        response = await client.get(path)
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "catalog.not_found"


async def test_market_price_filter_and_persian_multiple_tokens(api):
    client, _ = api
    iran = (await client.get("/api/v1/catalog/products?market=ir&max_price=2000000000")).json()
    international = (
        await client.get("/api/v1/catalog/products?market=international&max_price=50000")
    ).json()
    assert iran["total"] == 1 and international["total"] == 2
    graphics = (
        await client.get("/api/v1/catalog/products", params={"q": "كارت\u200cگرافيك"})
    ).json()
    assert graphics["total"] == 1 and graphics["items"][0]["category"] == "gpu"


async def test_prefix_search_can_use_gin_index(api):
    _, session = api
    # Small seed sets normally prefer a sequential scan. This proves index
    # eligibility, not a benchmark or a forced production planner setting.
    await session.execute(text("SET LOCAL enable_seqscan = off"))
    rows = await session.scalars(
        text("EXPLAIN SELECT id FROM products WHERE search_tokens @> ARRAY['کیبو']::text[]")
    )
    assert "ix_products_search_tokens" in "\n".join(rows)


async def test_invalid_stored_facts_fail_closed_without_leaking_data(api):
    client, session = api
    product = (await client.get("/api/v1/catalog/products/amd-ryzen-7-9700x")).json()
    variant = product["variants"][0]
    await session.execute(
        update(VariantRow)
        .where(VariantRow.id == variant["id"])
        .values(
            specifications=variant["specifications"] | {"tdp_w": -1},
            spec_version=variant["spec_version"] + 1,
        )
    )
    response = await client.get("/api/v1/catalog/products/amd-ryzen-7-9700x")
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "catalog.invalid_data"
    assert "tdp_w" not in response.text


async def test_database_failure_is_a_sanitized_unavailable_response(api):
    from sqlalchemy.exc import OperationalError

    client, _ = api

    async def broken():
        raise OperationalError("private SQL", None, Exception("sensitive-password-marker"))
        yield  # Make this a failing dependency generator, like the real session boundary.

    original = app.dependency_overrides[session_dependency]
    app.dependency_overrides[session_dependency] = broken
    try:
        response = await client.get("/health/ready")
    finally:
        app.dependency_overrides[session_dependency] = original
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "catalog.unavailable"
    assert "sensitive-password-marker" not in response.text and "private SQL" not in response.text
