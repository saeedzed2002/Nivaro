"""Real SQL transactions through staff HTTP endpoints; each test rolls back its outer transaction."""

import asyncio
import os
from uuid import UUID, uuid4

import httpx
import pytest
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.ext.asyncio import AsyncSession

from nivaro_catalog.api.admin import database as admin_database
from nivaro_catalog.api.authorization import AdminPrincipal, AuthorizationError, catalog_admin
from nivaro_catalog.application.administration import transaction
from nivaro_catalog.domain.administration import AdministrationError, StockChange
from nivaro_catalog.infrastructure.database import Database
from nivaro_catalog.infrastructure.models import AuditRow, ProductRow, VariantRow
from nivaro_catalog.main import app
from nivaro_catalog.main import session as public_database
from nivaro_catalog.settings import Settings

pytestmark = pytest.mark.skipif(
    not os.getenv("CATALOG_DB_HOST"), reason="Explicit test database required"
)
ROOT = "/api/v1/admin/catalog/products"


@pytest.fixture
async def staff():
    database = Database(Settings())
    actor = uuid4()
    async with database.engine.connect() as connection:
        outer = await connection.begin()

        async def session():
            async with AsyncSession(
                bind=connection, expire_on_commit=False, join_transaction_mode="create_savepoint"
            ) as db:
                yield db

        async def principal():
            return AdminPrincipal(
                user_id=actor, session_id=uuid4(), kind="admin", permissions=["catalog.write"]
            )

        app.dependency_overrides.update(
            {admin_database: session, public_database: session, catalog_admin: principal}
        )
        try:
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://catalog.test"
            ) as client:
                yield client, connection, actor
        finally:
            app.dependency_overrides.clear()
            await outer.rollback()
    await database.engine.dispose()


async def draft(client):
    category = (await client.get("/api/v1/catalog/categories")).json()[0]["id"]
    body = {
        "slug": "test-" + uuid4().hex,
        "name": "Synthetic test product",
        "description": {"fa": "نمونه آزمون", "en": "Test only"},
        "category_id": category,
        "brand": "TEST",
        "highlights": ["Fixture"],
    }
    response = await client.post(ROOT, json=body, headers={"X-Request-ID": "test-create"})
    assert response.status_code == 201, response.text
    return response.json(), body


async def add_variant(client, product):
    body = {
        "expected_version": product["version"],
        "sku": "TEST-" + uuid4().hex.upper(),
        "packaging": {"fa": "آزمون", "en": "Test only"},
        "specifications": {"kind": "cpu", "model": "TEST-CPU"},
        "evidence": [],
    }
    response = await client.post(f"{ROOT}/{product['id']}/variants", json=body)
    assert response.status_code == 201, response.text
    return response.json(), body


async def test_draft_edit_conflicts_publication_and_audit(staff):
    client, connection, actor = staff
    product, body = await draft(client)
    url = f"{ROOT}/{product['id']}"
    assert product["version"] == 1 and product["status"] == "draft"
    assert product["image_ready"] is False and product["variants"] == []
    assert (await client.get("/api/v1/catalog/products/" + product["slug"])).status_code == 404
    duplicate = await client.post(ROOT, json=body)
    assert duplicate.status_code == 409 and "SQL" not in duplicate.text
    edited = await client.put(
        url, json=body | {"expected_version": 1, "name": "Updated test product"}
    )
    assert edited.status_code == 200, edited.text
    assert edited.json()["version"] == 2
    stale = await client.put(url, json=body | {"expected_version": 1})
    assert stale.status_code == 409 and stale.json()["error"]["code"] == "catalog.version_conflict"
    publish = await client.put(url + "/status", json={"expected_version": 2, "status": "published"})
    assert publish.status_code == 409
    product, _ = await add_variant(client, edited.json())
    assert (
        await client.put(url + "/status", json={"expected_version": 3, "status": "published"})
    ).status_code == 409
    # Only the trusted image pipeline may set readiness. Simulate its completed effect in fixture data.
    await connection.execute(
        update(ProductRow)
        .where(ProductRow.id == UUID(product["id"]))
        .values(image="cpu", image_ready=True)
    )
    published = await client.put(
        url + "/status", json={"expected_version": 3, "status": "published"}
    )
    assert published.status_code == 200, published.text
    assert (await client.get("/api/v1/catalog/products/" + product["slug"])).status_code == 200
    archived = await client.put(url + "/status", json={"expected_version": 4, "status": "archived"})
    assert archived.status_code == 200
    assert (await client.get("/api/v1/catalog/products/" + product["slug"])).status_code == 404
    audit = (await client.get(url + "/audit?page_size=2")).json()
    assert audit["total"] == 5 and len(audit["items"]) == 2
    assert all(item["actor_id"] == str(actor) for item in audit["items"])
    created = (
        (
            await connection.execute(
                select(AuditRow.__table__).where(
                    AuditRow.product_id == UUID(product["id"]), AuditRow.action == "product.created"
                )
            )
        )
        .mappings()
        .one()
    )
    assert created["before"] == {} and created["after"]["version"] == 1
    assert created["request_id"] == "test-create"


@pytest.mark.parametrize(
    "patch",
    [
        {"image_ready": True},
        {"status": "published"},
        {"image": "../../secret"},
        {"version": 99},
        {"slug": "invalid slug"},
        {"name": "   "},
        {"description": {"fa": " ", "en": "Test"}},
    ],
)
async def test_rejects_privileged_or_invalid_creation_fields(staff, patch):
    client, _, _ = staff
    _, body = await draft(client)
    response = await client.post(ROOT, json=body | patch)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "request.invalid"


async def test_variant_revisions_search_uniqueness_and_ownership(staff):
    client, _, _ = staff
    product, _ = await draft(client)
    product, body = await add_variant(client, product)
    variant = product["variants"][0]
    url = f"{ROOT}/{product['id']}/variants/{variant['id']}"
    edited = await client.put(
        url,
        json=body
        | {
            "expected_version": 2,
            "specifications": {"kind": "cpu", "model": "TEST-CPU", "cores": 8},
        },
    )
    assert edited.status_code == 200, edited.text
    changed = edited.json()["variants"][0]
    assert changed["spec_version"] == 2 and changed["version"] == 2
    assert (await client.get(ROOT, params={"q": body["sku"]})).json()["total"] == 1
    other, _ = await draft(client)
    cross = await client.put(
        f"{ROOT}/{other['id']}/variants/{variant['id']}", json=body | {"expected_version": 1}
    )
    assert cross.status_code == 404
    duplicate = await client.post(
        f"{ROOT}/{other['id']}/variants", json=body | {"expected_version": 1}
    )
    assert duplicate.status_code == 409
    assert (await client.get(f"{ROOT}/{other['id']}")).json()["version"] == 1
    kind = await client.put(
        url, json=body | {"expected_version": 3, "specifications": {"kind": "prebuilt"}}
    )
    assert kind.status_code == 409
    assert (
        await client.put(url, json=body | {"expected_version": 3, "reserved": 10})
    ).status_code == 422


async def test_stock_reserved_guard_retries_and_atomic_audit(staff):
    client, connection, actor = staff
    product, _ = await draft(client)
    product, _ = await add_variant(client, product)
    variant = product["variants"][0]
    url = f"{ROOT}/{product['id']}/variants/{variant['id']}/stock"
    body = {
        "expected_version": 2,
        "expected_stock_version": 1,
        "on_hand": 5,
        "stock_verified": True,
        "reason": "Physical count",
    }
    response = await client.put(url, json=body)
    assert response.status_code == 200, response.text
    assert response.json()["variants"][0]["on_hand"] == 5
    assert (await client.put(url, json=body)).status_code == 409
    await connection.execute(
        update(VariantRow).where(VariantRow.id == UUID(variant["id"])).values(reserved=4, version=3)
    )
    # A reservation may advance stock without advancing the product editor revision.
    assert (
        await client.put(url, json=body | {"expected_version": 3, "expected_stock_version": 2})
    ).json()["error"]["code"] == "catalog.stock_version_conflict"
    below = await client.put(
        url, json=body | {"expected_version": 3, "expected_stock_version": 3, "on_hand": 3}
    )
    assert below.status_code == 409 and below.json()["error"]["code"] == "catalog.stock_reserved"
    assert (
        await client.put(
            url, json=body | {"expected_version": 3, "expected_stock_version": 3, "reason": " "}
        )
    ).status_code == 422
    rows = (
        (
            await connection.execute(
                select(AuditRow.__table__).where(
                    AuditRow.product_id == UUID(product["id"]), AuditRow.action == "stock.adjusted"
                )
            )
        )
        .mappings()
        .all()
    )
    assert len(rows) == 1 and rows[0]["actor_id"] == actor
    assert rows[0]["before"]["on_hand"] == 0 and rows[0]["after"]["on_hand"] == 5
    assert rows[0]["reason"] == "Physical count"
    async with connection.begin_nested() as savepoint:
        with pytest.raises(IntegrityError):
            await connection.execute(
                update(AuditRow).where(AuditRow.id == rows[0]["id"]).values(reason="rewrite")
            )
        await savepoint.rollback()


async def test_independent_offers_and_stale_price_guard(staff):
    client, connection, _ = staff
    product, _ = await draft(client)
    product, _ = await add_variant(client, product)
    variant = product["variants"][0]
    url = f"{ROOT}/{product['id']}/variants/{variant['id']}/offers"
    body = {
        "expected_version": 2,
        "expected_price_version": 0,
        "market": "ir",
        "currency": "IRR",
        "amount_minor": 100000,
        "available_for_sale": False,
        "reference_only": True,
        "source": {
            "url": "https://example.test/offer",
            "checked_on": "2026-10-29",
            "note": "Synthetic test",
        },
        "seller": "TEST",
        "reason": "Test observation",
    }
    assert (await client.put(url, json=body | {"currency": "USD"})).status_code == 422
    assert (await client.put(url, json=body | {"amount_minor": 101})).status_code == 422
    assert (await client.put(url, json=body | {"amount_minor": True})).status_code == 422
    assert (await client.put(url, json=body | {"available_for_sale": True})).status_code == 422
    assert (
        await client.put(url, json=body | {"available_for_sale": True, "reference_only": False})
    ).status_code == 409
    first = await client.put(url, json=body)
    assert first.status_code == 200, first.text
    second = await client.put(
        url,
        json=body
        | {
            "expected_version": 3,
            "market": "international",
            "currency": "USD",
            "amount_minor": 12345,
        },
    )
    assert second.status_code == 200, second.text
    offers = {o["market"]: o for o in second.json()["variants"][0]["offers"]}
    assert (
        offers["ir"]["amount_minor"] == 100000 and offers["international"]["amount_minor"] == 12345
    )
    assert (await client.put(url, json=body | {"expected_version": 4})).json()["error"][
        "code"
    ] == "catalog.price_version_conflict"
    third = await client.put(
        url,
        json=body | {"expected_version": 4, "expected_price_version": 1, "amount_minor": 200000},
    )
    assert third.status_code == 200, third.text
    iran = next(o for o in third.json()["variants"][0]["offers"] if o["market"] == "ir")
    assert iran["price_version"] == 2
    assert (
        await connection.scalar(
            select(func.count())
            .select_from(AuditRow)
            .where(AuditRow.product_id == UUID(product["id"]), AuditRow.action == "offer.changed")
        )
        == 3
    )


async def test_audit_write_failure_rolls_back_product(staff, monkeypatch):
    from nivaro_catalog.application.administration import Administration

    client, _, _ = staff
    product, body = await draft(client)

    def broken(*args, **kwargs):
        raise OperationalError("hidden SQL", {}, Exception("secret-marker"))

    monkeypatch.setattr(Administration, "audit", broken)
    response = await client.put(
        f"{ROOT}/{product['id']}", json=body | {"expected_version": 1, "name": "Must roll back"}
    )
    assert response.status_code == 503 and "secret-marker" not in response.text
    fresh = (await client.get(f"{ROOT}/{product['id']}")).json()
    assert fresh["version"] == 1 and fresh["name"] == body["name"]


async def test_all_write_routes_require_fresh_authorization_before_effect(staff):
    client, connection, _ = staff
    product, body = await draft(client)
    product, variant_body = await add_variant(client, product)
    url = f"{ROOT}/{product['id']}"
    variant_url = url + "/variants/" + product["variants"][0]["id"]
    routes = [
        ("POST", ROOT, body),
        ("PUT", url, body | {"expected_version": 2}),
        ("PUT", url + "/status", {"expected_version": 2, "status": "archived"}),
        ("POST", url + "/variants", variant_body),
        ("PUT", variant_url, variant_body),
        ("PUT", variant_url + "/stock", {}),
        ("PUT", variant_url + "/offers", {}),
    ]
    before = await connection.scalar(select(func.count()).select_from(AuditRow))
    app.dependency_overrides.pop(catalog_admin)
    for method, path, payload in routes:
        assert (await client.request(method, path, json=payload)).status_code == 401

    async def revoked():
        raise AuthorizationError("auth.forbidden", 403)

    app.dependency_overrides[catalog_admin] = revoked
    for method, path, payload in routes:
        assert (await client.request(method, path, json=payload)).status_code == 403
    assert await connection.scalar(select(func.count()).select_from(AuditRow)) == before


@pytest.mark.skipif(
    os.getenv("CATALOG_DISPOSABLE_TESTS") != "1",
    reason="Committed concurrency probe requires disposable database opt-in",
)
async def test_competing_stock_writes_commit_once_and_loser_conflicts():
    """Two real sessions; first holds locks until the second has attempted its write."""
    database = Database(Settings())
    async with database.sessions() as db:
        variant = await db.scalar(select(VariantRow).order_by(VariantRow.id).limit(1))
        product = await db.get(ProductRow, variant.product_id)
        pid, vid, version, stock_version = product.id, variant.id, product.version, variant.version
        original_stock, original_verified = variant.on_hand, variant.stock_verified
        audit_count = await db.scalar(
            select(func.count())
            .select_from(AuditRow)
            .where(AuditRow.target_id == vid, AuditRow.action == "stock.adjusted")
        )
    started = asyncio.Event()
    actor = uuid4()
    command = StockChange(
        expected_version=version,
        expected_stock_version=stock_version,
        on_hand=original_stock + 1,
        stock_verified=True,
        reason="Disposable race fixture",
    )

    async def second():
        async with database.sessions() as db:
            started.set()
            async with transaction(db, actor, "race-loser") as service:
                await service.stock(
                    pid, vid, command.model_copy(update={"on_hand": original_stock + 2})
                )

    loser = None
    try:
        async with database.sessions() as db:
            async with transaction(db, actor, "race-winner") as service:
                await service.stock(pid, vid, command)
                await db.flush()
                loser = asyncio.create_task(second())
                await started.wait()
                await asyncio.sleep(0.05)
                assert not loser.done(), "Second writer must wait for the held product lock"
        with pytest.raises(AdministrationError, match="Reload") as failure:
            await asyncio.wait_for(loser, timeout=5)
        assert failure.value.code == "catalog.version_conflict"
        async with database.sessions() as db:
            fresh = await db.get(VariantRow, vid)
            assert fresh.on_hand == original_stock + 1 and fresh.version == stock_version + 1
            assert (
                await db.scalar(
                    select(func.count())
                    .select_from(AuditRow)
                    .where(AuditRow.target_id == vid, AuditRow.action == "stock.adjusted")
                )
                == audit_count + 1
            )
    finally:
        if loser and not loser.done():
            loser.cancel()
            await asyncio.gather(loser, return_exceptions=True)
        # Preserve fixture display/stock for subsequent suites. Keep monotonic revisions
        # and audit history until this entire disposable database is discarded.
        async with database.sessions() as db, db.begin():
            await db.execute(
                update(VariantRow)
                .where(VariantRow.id == vid)
                .values(
                    on_hand=original_stock,
                    stock_verified=original_verified,
                    version=VariantRow.version + 1,
                )
            )
        await database.engine.dispose()
