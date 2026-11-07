"""Catalog-owned media transactions; caller controls transaction boundaries.

Mutation/activation lock order: product, slot, job. Claim/recovery lock jobs only.
No filesystem, decoder, or broker operation is performed while locks are held.
"""

from datetime import datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from nivaro_catalog.domain.administration import AdministrationError
from nivaro_catalog.infrastructure.models import (
    AuditRow,
    MediaDispatchRow,
    MediaJobRow,
    MediaSlotRow,
    ProductRow,
)

LEASE = timedelta(seconds=90)


async def database_now(db: AsyncSession) -> datetime:
    value = (await db.execute(select(func.clock_timestamp()))).scalar_one()
    assert isinstance(value, datetime)
    return value


async def queue_image(
    db: AsyncSession,
    *,
    product_id: UUID,
    position: int,
    expected_version: int,
    job_id: UUID,
    actor_id: UUID,
    alt: dict[str, str],
    request_id: str,
    image_kind: str = "illustration",
) -> UUID:
    product = await db.scalar(
        select(ProductRow).where(ProductRow.id == product_id).with_for_update()
    )
    if product is None:
        raise AdministrationError("catalog.not_found", "Product not found", 404)
    if product.version != expected_version:
        raise AdministrationError("catalog.version_conflict", "Product changed")
    if (
        position not in range(8)
        or set(alt) != {"fa", "en"}
        or any(not v.strip() or len(v) > 240 for v in alt.values())
        or image_kind not in {"illustration", "exact_sku"}
    ):
        raise AdministrationError("request.invalid", "Invalid image metadata", 422)
    slot = await db.scalar(
        select(MediaSlotRow)
        .where(MediaSlotRow.product_id == product_id, MediaSlotRow.position == position)
        .with_for_update()
    )
    if slot is None:
        slot = MediaSlotRow(id=uuid4(), product_id=product_id, position=position, alt=alt)
        db.add(slot)
        await db.flush()
    previous = slot.desired_job_id
    slot.desired_job_id = job_id
    # Alternative text is activated with the successful candidate, not a failed replacement.
    job = MediaJobRow(
        id=job_id,
        slot_id=slot.id,
        actor_id=actor_id,
        state="uploaded",
        attempts=0,
        outputs={},
        alt=alt,
        image_kind=image_kind,
    )
    db.add(job)
    await db.flush()
    db.add(MediaDispatchRow(job_id=job_id))
    product.version += 1
    db.add(
        AuditRow(
            id=uuid4(),
            product_id=product_id,
            actor_id=actor_id,
            action="image.queued",
            target_id=job_id,
            before={"desired_job_id": str(previous) if previous else None},
            after={"position": position, "alt": alt},
            reason="",
            request_id=request_id,
        )
    )
    return slot.id


async def claim_job(db: AsyncSession, job_id: UUID) -> UUID | None:
    job = await db.scalar(select(MediaJobRow).where(MediaJobRow.id == job_id).with_for_update())
    if job is None or job.state != "uploaded" or job.attempts >= 3:
        return None
    now = await database_now(db)
    job.state, job.attempt_id = "processing", uuid4()
    job.attempts += 1
    job.lease_until = now + LEASE
    return job.attempt_id


async def finish_job(
    db: AsyncSession,
    job_id: UUID,
    attempt_id: UUID,
    *,
    outputs: dict[str, str] | None,
    error_code: str | None = None,
) -> bool:
    # Read immutable ownership first; then acquire locks in the global order.
    owner = (
        await db.execute(
            select(MediaSlotRow.product_id, MediaSlotRow.id)
            .join(MediaJobRow, MediaJobRow.slot_id == MediaSlotRow.id)
            .where(MediaJobRow.id == job_id)
        )
    ).one_or_none()
    if owner is None:
        return False
    product = await db.scalar(
        select(ProductRow).where(ProductRow.id == owner.product_id).with_for_update()
    )
    slot = await db.scalar(
        select(MediaSlotRow).where(MediaSlotRow.id == owner.id).with_for_update()
    )
    job = await db.scalar(select(MediaJobRow).where(MediaJobRow.id == job_id).with_for_update())
    assert product is not None and slot is not None and job is not None
    now = await database_now(db)
    if (
        job.state != "processing"
        or job.attempt_id != attempt_id
        or job.lease_until is None
        or job.lease_until <= now
    ):
        return False
    job.finished_at, job.lease_until = now, None
    if slot.desired_job_id != job_id:
        job.state, job.error_code = "failed", "superseded"
        return False
    if error_code or not outputs:
        job.state, job.error_code = "failed", error_code or "empty_outputs"
        return False
    if not outputs.keys() <= {"320", "640", "1280"} or any(
        path != f"{attempt_id.hex}/{width}.webp" for width, path in outputs.items()
    ):
        raise ValueError("Invalid worker output manifest")
    before = slot.active_job_id
    job.state, job.outputs, job.error_code = "ready", outputs, None
    slot.active_job_id = job.id
    slot.alt = job.alt
    await update_cover(db, product)
    product.version += 1
    db.add(
        AuditRow(
            id=uuid4(),
            product_id=product.id,
            actor_id=job.actor_id,
            action="image.activated",
            target_id=job_id,
            before={"active_job_id": str(before) if before else None},
            after={"active_job_id": str(job_id)},
            reason="",
            request_id="media-worker",
        )
    )
    return True


async def update_cover(db: AsyncSession, product: ProductRow) -> None:
    await db.flush()
    cover = await db.scalar(
        select(MediaJobRow)
        .join(MediaSlotRow, MediaSlotRow.active_job_id == MediaJobRow.id)
        .where(MediaSlotRow.product_id == product.id)
        .order_by(MediaSlotRow.position)
        .limit(1)
    )
    if cover:
        product.image = f"media/{cover.id}/{max(cover.outputs, key=int)}"
        product.image_ready, product.image_kind = True, cover.image_kind
    elif product.image.startswith("media/"):
        if product.status == "published":
            raise AdministrationError(
                "catalog.image_required", "Unpublish before removing the last image", 409
            )
        product.image, product.image_ready = "", False


async def change_gallery(
    db: AsyncSession,
    *,
    product_id: UUID,
    position: int,
    expected_version: int,
    actor_id: UUID,
    request_id: str,
    destination: int | None = None,
) -> None:
    """Remove a slot's references or swap positions; never delete files inline."""
    product = await db.scalar(
        select(ProductRow).where(ProductRow.id == product_id).with_for_update()
    )
    if product is None:
        raise AdministrationError("catalog.not_found", "Product not found", 404)
    if product.version != expected_version:
        raise AdministrationError("catalog.version_conflict", "Product changed")
    slots = list(
        await db.scalars(
            select(MediaSlotRow).where(MediaSlotRow.product_id == product_id).with_for_update()
        )
    )
    slot = next((s for s in slots if s.position == position), None)
    if slot is None or (slot.active_job_id is None and slot.desired_job_id is None):
        raise AdministrationError("catalog.not_found", "Image not found", 404)
    before = {
        "position": position,
        "active_job_id": str(slot.active_job_id) if slot.active_job_id else None,
    }
    if destination is None:
        slot.active_job_id, slot.desired_job_id = None, None
        action = "image.removed"
    else:
        if destination not in range(8) or slot.active_job_id is None:
            raise AdministrationError("request.invalid", "Only ready images can be reordered", 422)
        other = next((s for s in slots if s.position == destination), None)
        if other:
            other.position = position
        slot.position = destination
        action = "image.moved"
    await update_cover(db, product)
    product.version += 1
    db.add(
        AuditRow(
            id=uuid4(),
            product_id=product_id,
            actor_id=actor_id,
            action=action,
            target_id=slot.id,
            before=before,
            after={"destination": destination},
            reason="",
            request_id=request_id,
        )
    )


async def recover_jobs(db: AsyncSession) -> int:
    now = await database_now(db)
    jobs = list(
        await db.scalars(
            select(MediaJobRow)
            .where(MediaJobRow.state == "processing", MediaJobRow.lease_until <= now)
            .with_for_update(skip_locked=True)
            .limit(50)
        )
    )
    for job in jobs:
        job.attempt_id, job.lease_until = None, None
        if job.attempts >= 3:
            job.state, job.error_code, job.finished_at = "failed", "worker_attempts_exhausted", now
        else:
            job.state = "uploaded"
            dispatch = await db.get(MediaDispatchRow, job.id)
            assert dispatch is not None
            dispatch.confirmed_at, dispatch.claim_id, dispatch.claimed_until = None, None, None
            dispatch.available_at = now + timedelta(seconds=2**job.attempts)
    # Broker confirmation is not evidence of consumption. Republish an unclaimed
    # uploaded job after a bounded interval (e.g. lost broker data); duplicate
    # deliveries are fenced by claim_job. Lock only dispatch rows in this query.
    stranded = list(
        await db.scalars(
            select(MediaDispatchRow)
            .join(MediaJobRow, MediaJobRow.id == MediaDispatchRow.job_id)
            .where(MediaJobRow.state == "uploaded", MediaDispatchRow.confirmed_at <= now - LEASE)
            .with_for_update(of=MediaDispatchRow, skip_locked=True)
            .limit(50)
        )
    )
    for entry in stranded:
        entry.confirmed_at, entry.claim_id, entry.claimed_until = None, None, None
        entry.available_at = now
    return len(jobs) + len(stranded)


async def claim_dispatch(db: AsyncSession) -> tuple[UUID, UUID] | None:
    now = await database_now(db)
    entry = await db.scalar(
        select(MediaDispatchRow)
        .where(
            MediaDispatchRow.confirmed_at.is_(None),
            MediaDispatchRow.available_at <= now,
            or_(MediaDispatchRow.claimed_until.is_(None), MediaDispatchRow.claimed_until <= now),
        )
        .order_by(MediaDispatchRow.available_at)
        .with_for_update(skip_locked=True)
        .limit(1)
    )
    if entry is None:
        return None
    entry.claim_id, entry.claimed_until = uuid4(), now + timedelta(seconds=20)
    return entry.job_id, entry.claim_id


async def confirm_dispatch(db: AsyncSession, job_id: UUID, claim_id: UUID) -> bool:
    entry = await db.scalar(
        select(MediaDispatchRow).where(MediaDispatchRow.job_id == job_id).with_for_update()
    )
    if entry is None or entry.claim_id != claim_id:
        return False
    entry.confirmed_at = await database_now(db)
    entry.claimed_until = None
    return True
