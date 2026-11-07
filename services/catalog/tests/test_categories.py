"""Two-level taxonomy with real SQL, audit rollback and concurrent structural edits."""

import asyncio
import os
from uuid import UUID, uuid4

import pytest
from sqlalchemy import event, func, select, update
from sqlalchemy.exc import IntegrityError, OperationalError
from test_administration import staff as staff

from nivaro_catalog.api.authorization import AuthorizationError, catalog_admin
from nivaro_catalog.application.administration import transaction
from nivaro_catalog.application.categories import save_category
from nivaro_catalog.domain.administration import AdministrationError, CategoryContent, CategoryEdit
from nivaro_catalog.infrastructure.database import Database
from nivaro_catalog.infrastructure.models import CategoryAuditRow, CategoryRow
from nivaro_catalog.main import app
from nivaro_catalog.settings import Settings

pytestmark = pytest.mark.skipif(
    not os.getenv("CATALOG_DB_HOST"), reason="Explicit test database required"
)
ROOT = "/api/v1/admin/catalog/categories"


def content(parent_id=None):
    return {
        "slug": "test-category-" + uuid4().hex,
        "name": {"fa": "آزمون", "en": "Synthetic category"},
        "parent_id": parent_id,
    }


async def create(client, parent_id=None):
    body = content(parent_id)
    response = await client.post(ROOT, json=body)
    assert response.status_code == 201, response.text
    return response.json(), body


async def test_category_versions_depth_references_and_audit(staff):
    client, connection, actor = staff
    root, root_body = await create(client)
    child, child_body = await create(client, root["id"])
    assert root["version"] == 1 and root["product_count"] == 0
    assert (await client.post(ROOT, json=content(child["id"]))).status_code == 409
    assert (
        await client.put(
            f"{ROOT}/{root['id']}",
            json=root_body | {"expected_version": 1, "parent_id": root["id"]},
        )
    ).status_code == 409
    other, _ = await create(client)
    assert (
        await client.put(
            f"{ROOT}/{root['id']}",
            json=root_body | {"expected_version": 1, "parent_id": other["id"]},
        )
    ).status_code == 409
    assert (await client.post(ROOT, json=content(str(uuid4())))).status_code == 422
    assert (await client.post(ROOT, json=root_body)).status_code == 409
    changed_body = child_body | {"expected_version": 1, "name": {"fa": "نام جدید", "en": "Renamed"}}
    changed = await client.put(f"{ROOT}/{child['id']}", json=changed_body)
    assert changed.status_code == 200 and changed.json()["version"] == 2
    assert (await client.put(f"{ROOT}/{child['id']}", json=changed_body)).status_code == 409
    same = await client.put(f"{ROOT}/{child['id']}", json=changed_body | {"expected_version": 2})
    assert same.json()["version"] == 2
    public = (await client.get("/api/v1/catalog/categories")).json()
    assert next(row for row in public if row["id"] == child["id"])["name"]["en"] == "Renamed"
    rows = (await client.get(ROOT)).json()
    assert next(row for row in rows if row["id"] == root["id"])["child_count"] == 1
    audit = (await client.get(f"{ROOT}/{child['id']}/audit?page_size=1")).json()
    assert audit["total"] == 2 and len(audit["items"]) == 1
    assert audit["items"][0]["actor_id"] == str(actor)
    assert (await client.delete(f"{ROOT}/{root['id']}")).status_code == 405
    async with connection.begin_nested() as nested:
        with pytest.raises(IntegrityError):
            await connection.execute(update(CategoryAuditRow).values(reason="tamper"))
        await nested.rollback()


@pytest.mark.parametrize(
    "patch",
    [
        {"image": "https://untrusted.test/file"},
        {"version": 20},
        {"name": {"fa": " ", "en": "Valid"}},
        {"slug": "INVALID/SLUG"},
    ],
)
async def test_category_rejects_unowned_or_invalid_fields(staff, patch):
    client, _, _ = staff
    assert (await client.post(ROOT, json=content() | patch)).status_code == 422


async def test_category_audit_failure_rolls_back_every_change(staff):
    client, connection, _ = staff
    row, body = await create(client)

    def fail(*args):
        raise OperationalError("hidden SQL", {}, Exception("category-secret-marker"))

    event.listen(CategoryAuditRow, "before_insert", fail)
    try:
        response = await client.put(
            f"{ROOT}/{row['id']}",
            json=body | {"expected_version": 1, "name": {"fa": "تغییر", "en": "Must roll back"}},
        )
        assert response.status_code == 503 and "category-secret-marker" not in response.text
    finally:
        event.remove(CategoryAuditRow, "before_insert", fail)
    stored = (
        await connection.execute(
            select(CategoryRow.name, CategoryRow.version).where(CategoryRow.id == UUID(row["id"]))
        )
    ).one()
    assert stored.name == body["name"] and stored.version == 1


async def test_category_routes_require_fresh_staff_authority(staff):
    client, connection, _ = staff
    row, body = await create(client)
    routes = [
        ("GET", ROOT, None),
        ("GET", f"{ROOT}/{row['id']}/audit", None),
        ("POST", ROOT, content()),
        ("PUT", f"{ROOT}/{row['id']}", body | {"expected_version": 1}),
    ]
    before = await connection.scalar(select(func.count()).select_from(CategoryAuditRow))
    app.dependency_overrides.pop(catalog_admin)
    for method, path, payload in routes:
        assert (await client.request(method, path, json=payload)).status_code == 401

    async def denied():
        raise AuthorizationError("auth.forbidden", 403)

    app.dependency_overrides[catalog_admin] = denied
    for method, path, payload in routes:
        assert (await client.request(method, path, json=payload)).status_code == 403
    assert await connection.scalar(select(func.count()).select_from(CategoryAuditRow)) == before


@pytest.mark.skipif(
    os.getenv("CATALOG_DISPOSABLE_TESTS") != "1",
    reason="Committed race requires disposable database opt-in",
)
async def test_competing_parent_moves_cannot_create_a_cycle():
    database = Database(Settings())
    actor = uuid4()
    async with database.sessions() as db, transaction(db, actor, "category-race-setup") as service:
        left_body, right_body = content(), content()
        left = await save_category(service, CategoryContent.model_validate(left_body))
        right = await save_category(service, CategoryContent.model_validate(right_body))
    started = asyncio.Event()

    async def second():
        async with (
            database.sessions() as db,
            transaction(db, actor, "category-race-loser") as service,
        ):
            started.set()
            await save_category(
                service,
                CategoryEdit.model_validate(
                    right_body | {"expected_version": 1, "parent_id": str(left)}
                ),
                right,
            )

    loser = None
    try:
        async with (
            database.sessions() as db,
            transaction(db, actor, "category-race-winner") as service,
        ):
            await save_category(
                service,
                CategoryEdit.model_validate(
                    left_body | {"expected_version": 1, "parent_id": str(right)}
                ),
                left,
            )
            loser = asyncio.create_task(second())
            await started.wait()
            await asyncio.sleep(0.05)
            assert not loser.done()
        with pytest.raises(AdministrationError) as failure:
            await asyncio.wait_for(loser, timeout=5)
        assert failure.value.code == "catalog.category_hierarchy"
        async with database.sessions() as db:
            a, b = await db.get(CategoryRow, left), await db.get(CategoryRow, right)
            assert a.parent_id == right and b.parent_id is None
            assert a.version == 2 and b.version == 1
    finally:
        if loser and not loser.done():
            loser.cancel()
            await asyncio.gather(loser, return_exceptions=True)
        await database.engine.dispose()
