from uuid import UUID

from sqlalchemy import select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession

from nivaro_payments.attempts import read_attempt
from nivaro_payments.contracts import AttemptState, Market, OperationsAttempt, OperationsPage
from nivaro_payments.models import Attempt


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
