from uuid import UUID

from sqlalchemy import select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession

from nivaro_payments.attempts import apply_observation, database_time, read_attempt
from nivaro_payments.contracts import (
    AttemptState,
    Market,
    OperationsAttempt,
    OperationsDetail,
    OperationsPage,
    PaymentError,
    ReconciliationResult,
    ReconciliationView,
)
from nivaro_payments.models import Attempt, ReconciliationRun
from nivaro_payments.provider import Provider


async def reconcile_attempt(
    db: AsyncSession, provider: Provider, attempt_id: UUID, operation_id: UUID, actor_id: UUID
) -> ReconciliationView:
    async with db.begin():
        attempt = await read_attempt(db, attempt_id, lock=True)
        previous = await db.get(ReconciliationRun, (attempt_id, operation_id))
        if previous is not None:
            if previous.actor_id != actor_id:
                raise PaymentError("payment.idempotency_conflict")
            return ReconciliationView.model_validate(previous)

        now = await database_time(db)
        before = attempt.status
        result: ReconciliationResult = "already_final"
        if attempt.verified_at is None:
            try:
                apply_observation(db, provider, attempt, now, query=True)
                result = "observed"
            except PaymentError as exc:
                if exc.code == "provider.unavailable":
                    result = "provider_unavailable"
                elif exc.code == "provider.evidence_mismatch":
                    result = "evidence_mismatch"
                else:
                    raise
        run = ReconciliationRun(
            attempt_id=attempt_id,
            operation_id=operation_id,
            actor_id=actor_id,
            checked_at=now,
            status_before=before,
            status_after=attempt.status,
            result=result,
        )
        db.add(run)
        return ReconciliationView.model_validate(run)


async def read_operation(db: AsyncSession, attempt_id: UUID) -> OperationsDetail:
    # Use one statement so the latest audit and displayed attempt are from the same snapshot.
    latest = (
        select(ReconciliationRun.operation_id)
        .where(ReconciliationRun.attempt_id == Attempt.id)
        .order_by(ReconciliationRun.checked_at.desc(), ReconciliationRun.operation_id.desc())
        .limit(1)
        .correlate(Attempt)
        .scalar_subquery()
    )
    row = (
        await db.execute(
            select(Attempt, ReconciliationRun)
            .outerjoin(
                ReconciliationRun,
                (ReconciliationRun.attempt_id == Attempt.id)
                & (ReconciliationRun.operation_id == latest),
            )
            .where(Attempt.id == attempt_id)
        )
    ).one_or_none()
    if row is None:
        raise PaymentError("payment.not_found", 404)
    attempt, run = row
    return OperationsDetail(
        **OperationsAttempt.model_validate(attempt).model_dump(),
        last_reconciliation=ReconciliationView.model_validate(run) if run is not None else None,
    )


async def list_attempts(
    db: AsyncSession,
    *,
    status: AttemptState | None,
    market: Market | None,
    order_id: UUID | None,
    before: UUID | None,
    limit: int,
) -> OperationsPage:
    query = select(Attempt).order_by(Attempt.created_at.desc(), Attempt.id.desc()).limit(limit + 1)
    if status is not None:
        query = query.where(Attempt.status == status)
    if market is not None:
        query = query.where(Attempt.market == market)
    if order_id is not None:
        query = query.where(Attempt.order_id == order_id)
    if before is not None:
        boundary = await read_attempt(db, before)
        query = query.where(
            tuple_(Attempt.created_at, Attempt.id) < tuple_(boundary.created_at, boundary.id)
        )
    rows = (await db.scalars(query)).all()
    return OperationsPage(
        attempts=[OperationsAttempt.model_validate(row) for row in rows[:limit]],
        next_before=rows[limit - 1].id if len(rows) > limit else None,
    )
