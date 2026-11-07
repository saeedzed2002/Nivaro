"""Real database tests; fixtures roll back all media and product mutations."""

import os
from datetime import timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy import event, func, select
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession
from test_administration import draft
from test_administration import staff as staff

from nivaro_catalog.application.media import (
    change_gallery,
    claim_dispatch,
    claim_job,
    confirm_dispatch,
    finish_job,
    queue_image,
    recover_jobs,
)
from nivaro_catalog.domain.administration import AdministrationError
from nivaro_catalog.infrastructure.models import (
    AuditRow,
    MediaDispatchRow,
    MediaJobRow,
    MediaSlotRow,
    ProductRow,
)

pytestmark = pytest.mark.skipif(
    not os.getenv("CATALOG_DB_HOST"), reason="Explicit test database required"
)


async def queued(db, product_id, actor, position=0, alt=None):
    product = await db.get(ProductRow, product_id)
    job = uuid4()
    slot = await queue_image(
        db,
        product_id=product_id,
        position=position,
        expected_version=product.version,
        actor_id=actor,
        job_id=job,
        alt=alt or {"fa": "تصویر", "en": "Image"},
        request_id="media-test",
    )
    await db.flush()
    return job, slot


def outputs(attempt):
    return {"320": f"{attempt.hex}/320.webp", "640": f"{attempt.hex}/640.webp"}


async def test_gallery_order_removal_and_pending_activation_fence(staff):
    client, connection, actor = staff
    product, _ = await draft(client)
    async with (
        AsyncSession(
            bind=connection, expire_on_commit=False, join_transaction_mode="create_savepoint"
        ) as db,
        db.begin(),
    ):
        pid = UUID(product["id"])
        first, first_slot = await queued(db, pid, actor, position=0)
        second, second_slot = await queued(db, pid, actor, position=1)
        for job in (first, second):
            attempt = await claim_job(db, job)
            assert await finish_job(db, job, attempt, outputs=outputs(attempt))
        row = await db.get(ProductRow, pid)
        assert str(first) in row.image
        await change_gallery(
            db,
            product_id=pid,
            position=1,
            destination=0,
            expected_version=row.version,
            actor_id=actor,
            request_id="test",
        )
        assert str(second) in row.image
        assert (await db.get(MediaSlotRow, first_slot)).position == 1
        assert (await db.get(MediaSlotRow, second_slot)).position == 0
        with pytest.raises(AdministrationError, match="Product changed"):
            await change_gallery(
                db,
                product_id=pid,
                position=0,
                expected_version=row.version - 1,
                actor_id=actor,
                request_id="test",
            )
        pending, _ = await queued(db, pid, actor, position=0)
        candidate = await claim_job(db, pending)
        await change_gallery(
            db,
            product_id=pid,
            position=0,
            expected_version=row.version,
            actor_id=actor,
            request_id="test",
        )
        assert str(first) in row.image
        assert not await finish_job(db, pending, candidate, outputs=outputs(candidate))
        row.status = "published"
        with pytest.raises(AdministrationError, match="Unpublish"):
            async with db.begin_nested():
                await change_gallery(
                    db,
                    product_id=pid,
                    position=1,
                    expected_version=row.version,
                    actor_id=actor,
                    request_id="test",
                )
        await db.refresh(row)
        assert str(first) in row.image and row.image_ready
        row.status = "draft"
        await change_gallery(
            db,
            product_id=pid,
            position=1,
            expected_version=row.version,
            actor_id=actor,
            request_id="test",
        )
        assert not row.image and not row.image_ready


async def test_activation_duplicate_delivery_and_failed_replacement(staff):
    client, connection, actor = staff
    product, _ = await draft(client)
    async with (
        AsyncSession(
            bind=connection, expire_on_commit=False, join_transaction_mode="create_savepoint"
        ) as db,
        db.begin(),
    ):
        product_id = UUID(product["id"])
        first, slot_id = await queued(db, product_id, actor)
        dispatch = await claim_dispatch(db)
        assert dispatch[0] == first
        assert await claim_dispatch(db) is None
        assert not await confirm_dispatch(db, first, uuid4())
        assert await confirm_dispatch(db, *dispatch)
        attempt = await claim_job(db, first)
        assert attempt and await claim_job(db, first) is None
        assert await finish_job(db, first, attempt, outputs=outputs(attempt))
        assert not await finish_job(db, first, attempt, outputs=outputs(attempt))
        slot = await db.get(MediaSlotRow, slot_id)
        stored_product = await db.get(ProductRow, product_id)
        previous_image = stored_product.image
        assert stored_product.image_kind == "illustration"
        second, _ = await queued(db, product_id, actor, alt={"fa": "جدید", "en": "New"})
        second_attempt = await claim_job(db, second)
        assert not await finish_job(
            db, second, second_attempt, outputs=None, error_code="invalid_image"
        )
        assert slot.active_job_id == first and slot.alt["en"] == "Image"
        assert stored_product.image == previous_image
        assert (await db.get(MediaJobRow, second)).state == "failed"


async def test_recovery_fences_stale_attempt_and_exhausts_retries(staff):
    client, connection, actor = staff
    product, _ = await draft(client)
    async with (
        AsyncSession(
            bind=connection, expire_on_commit=False, join_transaction_mode="create_savepoint"
        ) as db,
        db.begin(),
    ):
        job_id, slot_id = await queued(db, UUID(product["id"]), actor)
        original_attempt = await claim_job(db, job_id)
        job = await db.get(MediaJobRow, job_id)
        now = await db.scalar(select(func.now()))
        job.lease_until = now - timedelta(seconds=1)
        await db.flush()
        assert await recover_jobs(db) == 1
        assert not await finish_job(db, job_id, original_attempt, outputs=outputs(original_attempt))
        second = await claim_job(db, job_id)
        assert second != original_attempt
        assert not await finish_job(db, job_id, original_attempt, outputs=outputs(original_attempt))
        for _ in range(2):
            job.lease_until = now - timedelta(seconds=1)
            await db.flush()
            await recover_jobs(db)
            if job.state == "uploaded":
                await claim_job(db, job_id)
        assert job.state == "failed" and job.attempts == 3
        assert await claim_job(db, job_id) is None
        assert (await db.get(MediaSlotRow, slot_id)).active_job_id is None


async def test_new_candidate_fences_old_job_and_stranded_dispatch_recovers(staff):
    client, connection, actor = staff
    product, _ = await draft(client)
    async with (
        AsyncSession(
            bind=connection, expire_on_commit=False, join_transaction_mode="create_savepoint"
        ) as db,
        db.begin(),
    ):
        product_id = UUID(product["id"])
        old, slot_id = await queued(db, product_id, actor)
        attempt = await claim_job(db, old)
        new, _ = await queued(db, product_id, actor)
        assert not await finish_job(db, old, attempt, outputs=outputs(attempt))
        assert (await db.get(MediaJobRow, old)).error_code == "superseded"
        entry = await db.get(MediaDispatchRow, new)
        entry.confirmed_at = (await db.scalar(select(func.now()))) - timedelta(minutes=5)
        await db.flush()
        assert await recover_jobs(db) == 1
        assert entry.confirmed_at is None
        new_attempt = await claim_job(db, new)
        assert await finish_job(db, new, new_attempt, outputs=outputs(new_attempt))
        assert (await db.get(MediaSlotRow, slot_id)).active_job_id == new


async def test_queue_audit_failure_rolls_back_job_slot_dispatch_and_product(staff):
    client, connection, actor = staff
    product, _ = await draft(client)

    def fail(*args):
        raise OperationalError("hidden", {}, Exception("simulated failure"))

    event.listen(AuditRow, "before_insert", fail)
    try:
        with pytest.raises(OperationalError):
            async with (
                AsyncSession(
                    bind=connection,
                    expire_on_commit=False,
                    join_transaction_mode="create_savepoint",
                ) as db,
                db.begin(),
            ):
                await queued(db, UUID(product["id"]), actor)
    finally:
        event.remove(AuditRow, "before_insert", fail)
    assert await connection.scalar(select(func.count()).select_from(MediaJobRow)) == 0
    assert await connection.scalar(select(func.count()).select_from(MediaDispatchRow)) == 0
    assert await connection.scalar(select(func.count()).select_from(MediaSlotRow)) == 0
    assert (
        await connection.scalar(
            select(ProductRow.version).where(ProductRow.id == UUID(product["id"]))
        )
        == product["version"]
    )


async def test_gallery_limit_and_stale_product_version(staff):
    client, connection, actor = staff
    product, _ = await draft(client)
    async with (
        AsyncSession(
            bind=connection, expire_on_commit=False, join_transaction_mode="create_savepoint"
        ) as db,
        db.begin(),
    ):
        for position in range(8):
            await queued(db, UUID(product["id"]), actor, position)
        with pytest.raises(AdministrationError, match="Invalid image metadata"):
            await queued(db, UUID(product["id"]), actor, 8)
        with pytest.raises(AdministrationError, match="Product changed"):
            await queue_image(
                db,
                product_id=UUID(product["id"]),
                position=0,
                expected_version=1,
                actor_id=actor,
                job_id=uuid4(),
                alt={"fa": "آزمون", "en": "Test"},
                request_id="stale",
            )
