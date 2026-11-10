"""Identity-owned avatar lifecycle. Caller commits before storage/broker I/O."""

from datetime import datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from nivaro_identity.domain.errors import IdentityError
from nivaro_identity.domain.security import SessionKind
from nivaro_identity.infrastructure.models import Audit, AvatarDispatch, AvatarJob, AvatarSlot

LEASE = timedelta(seconds=90)


async def database_now(db: AsyncSession) -> datetime:
    value = (await db.execute(select(func.clock_timestamp()))).scalar_one()
    assert isinstance(value, datetime)
    return value


async def get_slot(
    db: AsyncSession, owner: UUID, kind: SessionKind, *, lock: bool = False
) -> AvatarSlot | None:
    query = select(AvatarSlot).where(AvatarSlot.user_id == owner, AvatarSlot.kind == kind)
    return await db.scalar(query.with_for_update() if lock else query)


async def update_slot(
    db: AsyncSession, owner: UUID, kind: SessionKind, version: int, job_id: UUID | None
) -> None:
    """Authenticated mutation already holds this user's lock, including first slot creation."""
    slot = await get_slot(db, owner, kind, lock=True)
    if version != (slot.version if slot else 0):
        raise IdentityError("avatar.changed", 409)
    if job_id is None and (slot is None or not (slot.active_job_id or slot.desired_job_id)):
        return
    if slot is None:
        slot = AvatarSlot(user_id=owner, kind=kind, version=1)
        db.add(slot)
        await db.flush()
    else:
        slot.version += 1
    slot.desired_job_id = job_id
    if job_id is None:
        slot.active_job_id = None
    else:
        db.add(AvatarJob(id=job_id, slot_id=slot.id))
        await db.flush()
        db.add(AvatarDispatch(job_id=job_id))
    db.add(Audit(user_id=owner, event=f"{kind}.avatar.{'queued' if job_id else 'removed'}"))


async def finish_job(
    db: AsyncSession, job_id: UUID, attempt_id: UUID, error_code: str | None = None
) -> bool:
    slot = await db.scalar(
        select(AvatarSlot)
        .join(AvatarJob, AvatarJob.slot_id == AvatarSlot.id)
        .where(AvatarJob.id == job_id)
        .with_for_update(of=AvatarSlot)
    )
    if slot is None:
        return False
    job = await db.scalar(select(AvatarJob).where(AvatarJob.id == job_id).with_for_update())
    now = await database_now(db)
    if (
        job is None
        or job.state != "processing"
        or job.attempt_id != attempt_id
        or job.lease_until is None
        or job.lease_until <= now
    ):
        return False
    job.finished_at, job.lease_until = now, None
    if slot.desired_job_id != job.id:
        error_code = "superseded"
    if error_code:
        job.state, job.error_code = "failed", error_code
        return False
    job.state = "ready"
    slot.active_job_id = job.id
    slot.version += 1
    db.add(Audit(user_id=slot.user_id, event=f"{slot.kind}.avatar.activated"))
    return True


async def claim_job(db: AsyncSession, job_id: UUID) -> UUID | None:
    job = await db.scalar(select(AvatarJob).where(AvatarJob.id == job_id).with_for_update())
    if job is None or job.state != "uploaded" or job.attempts >= 3:
        return None
    now = await database_now(db)
    job.state, job.attempt_id = "processing", uuid4()
    job.attempts += 1
    job.lease_until = now + LEASE
    return job.attempt_id


async def recover_jobs(db: AsyncSession) -> int:
    now = await database_now(db)
    jobs = list(
        await db.scalars(
            select(AvatarJob)
            .where(AvatarJob.state == "processing", AvatarJob.lease_until <= now)
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
            dispatch = await db.get(AvatarDispatch, job.id)
            assert dispatch is not None
            dispatch.confirmed_at, dispatch.claim_id, dispatch.claimed_until = None, None, None
            dispatch.available_at = now + timedelta(seconds=2**job.attempts)
    # Broker confirmation is not evidence of consumption. Republish an unclaimed
    # uploaded job after a bounded interval (e.g. lost broker data); duplicate
    # deliveries are fenced by claim_job. Lock only dispatch rows in this query.
    stranded = list(
        await db.scalars(
            select(AvatarDispatch)
            .join(AvatarJob, AvatarJob.id == AvatarDispatch.job_id)
            .where(AvatarJob.state == "uploaded", AvatarDispatch.confirmed_at <= now - LEASE)
            .with_for_update(of=AvatarDispatch, skip_locked=True)
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
        select(AvatarDispatch)
        .where(
            AvatarDispatch.confirmed_at.is_(None),
            AvatarDispatch.available_at <= now,
            or_(AvatarDispatch.claimed_until.is_(None), AvatarDispatch.claimed_until <= now),
        )
        .order_by(AvatarDispatch.available_at)
        .with_for_update(skip_locked=True)
        .limit(1)
    )
    if entry is None:
        return None
    entry.claim_id, entry.claimed_until = uuid4(), now + timedelta(seconds=20)
    return entry.job_id, entry.claim_id


async def confirm_dispatch(db: AsyncSession, job_id: UUID, claim_id: UUID) -> bool:
    entry = await db.scalar(
        select(AvatarDispatch).where(AvatarDispatch.job_id == job_id).with_for_update()
    )
    if entry is None or entry.claim_id != claim_id:
        return False
    entry.confirmed_at = await database_now(db)
    entry.claimed_until = None
    return True
