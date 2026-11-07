import os
from uuid import UUID, uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from test_administration import draft
from test_administration import staff as staff

from nivaro_catalog.api.authorization import catalog_admin
from nivaro_catalog.application.media import claim_job, finish_job
from nivaro_catalog.infrastructure.media_storage import MediaStorage
from nivaro_catalog.main import app

pytestmark = pytest.mark.skipif(
    not os.getenv("CATALOG_DB_HOST"), reason="Explicit test database required"
)


@pytest.fixture
def media_roots(tmp_path, monkeypatch):
    private, outputs = tmp_path / "private", tmp_path / "outputs"
    monkeypatch.setenv("CATALOG_MEDIA_PRIVATE_ROOT", str(private))
    monkeypatch.setenv("CATALOG_MEDIA_OUTPUT_ROOT", str(outputs))
    return MediaStorage(private, outputs)


async def test_upload_authority_bounds_status_and_private_outputs(staff, media_roots):
    client, connection, _ = staff
    product, _ = await draft(client)
    route = f"/api/v1/admin/catalog/products/{product['id']}/images/0"
    params = {"expected_version": product["version"], "alt_fa": "تصویر", "alt_en": "Image"}
    principal = app.dependency_overrides.pop(catalog_admin)
    assert (await client.put(route, params=params, content=b"input")).status_code == 401
    assert list(media_roots.private.iterdir()) == []
    app.dependency_overrides[catalog_admin] = principal
    assert (await client.put(route, params=params, content=b"")).status_code == 422
    assert (
        await client.put(route, params=params, content=b"x" * (8 * 1024 * 1024 + 1))
    ).status_code == 413
    response = await client.put(route, params=params, content=b"not decoded until worker")
    assert response.status_code == 202, response.text
    job = UUID(response.json()["id"])
    assert media_roots.read_original(job) == b"not decoded until worker"
    listing = await client.get(route.rsplit("/", 1)[0])
    assert listing.json()["items"][0]["pending"]["state"] == "uploaded"
    assert listing.json()["items"][0]["urls"] == {}
    assert listing.json()["version"] == product["version"] + 1
    assert (await client.get(f"/api/v1/catalog/images/{job}/320")).status_code == 404
    assert (await client.get(f"/api/v1/admin/catalog/images/{job}/320")).status_code == 404
    async with (
        AsyncSession(
            bind=connection, expire_on_commit=False, join_transaction_mode="create_savepoint"
        ) as db,
        db.begin(),
    ):
        attempt = await claim_job(db, job)
        paths = media_roots.write_outputs(attempt, {320: b"trusted-worker-fixture"})
        assert await finish_job(db, job, attempt, outputs={str(k): v for k, v in paths.items()})
    # A ready image of a draft remains private; a staff image requires staff cookies.
    assert (await client.get(f"/api/v1/catalog/images/{job}/320")).status_code == 404
    result = await client.get(f"/api/v1/admin/catalog/images/{job}/320")
    assert result.status_code == 200 and result.headers["content-type"] == "image/webp"
    app.dependency_overrides.pop(catalog_admin)
    assert (await client.get(f"/api/v1/admin/catalog/images/{job}/320")).status_code == 401
    assert (await client.get(f"/api/v1/catalog/images/{uuid4()}/320")).status_code == 404
