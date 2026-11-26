from typing import Literal
from uuid import UUID

from pydantic import AwareDatetime
from sqlalchemy import func, select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession

from nivaro_orders.domain.checkout import CheckoutError, Contract, Market, MarketTerms
from nivaro_orders.infrastructure.models import (
    Order,
    OrderPaymentAttempt,
    OrderPaymentCompensation,
    OrderPaymentRefund,
)

type CompensationState = Literal["pending", "awaiting_evidence", "completed", "manual_review"]
type RefundFilter = Literal[
    "open", "all", "pending", "awaiting_evidence", "completed", "manual_review"
]


class RefundQueueEntry(MarketTerms):
    refund_id: UUID
    attempt_id: UUID
    order_id: UUID
    state: CompensationState
    reason: str
    captured_minor: int
    confirmed_refund_minor: int
    verified_at: AwareDatetime
    retry_at: AwareDatetime | None
    last_error: str | None


class RefundQueue(Contract):
    refunds: list[RefundQueueEntry]
    next_before: UUID | None


async def list_refunds(
    db: AsyncSession,
    *,
    state: RefundFilter,
    market: Market | None,
    order_id: UUID | None,
    before: UUID | None,
    limit: int,
) -> RefundQueue:
    attempt = OrderPaymentAttempt
    compensation = OrderPaymentCompensation
    confirmed = (
        select(func.coalesce(func.sum(OrderPaymentRefund.amount_minor), 0))
        .where(OrderPaymentRefund.payment_attempt_id == attempt.id)
        .scalar_subquery()
    )
    query = (
        select(
            compensation.refund_id,
            compensation.attempt_id,
            attempt.order_id,
            compensation.state,
            compensation.reason,
            compensation.captured_minor,
            confirmed.label("confirmed_refund_minor"),
            attempt.verified_at,
            compensation.retry_at,
            compensation.last_error,
            Order.market,
            Order.currency,
        )
        .select_from(compensation)
        .join(attempt, attempt.id == compensation.attempt_id)
        .join(Order, Order.id == attempt.order_id)
        .where(attempt.verified_at.is_not(None))
        .order_by(attempt.verified_at.desc(), attempt.id.desc())
        .limit(limit + 1)
    )
    if state == "open":
        query = query.where(compensation.state != "completed")
    elif state != "all":
        query = query.where(compensation.state == state)
    if market is not None:
        query = query.where(Order.market == market)
    if order_id is not None:
        query = query.where(Order.id == order_id)
    if before is not None:
        boundary = await db.scalar(
            select(attempt.verified_at)
            .join(compensation, compensation.attempt_id == attempt.id)
            .where(attempt.id == before)
        )
        if boundary is None:
            raise CheckoutError("checkout.not_found")
        query = query.where(tuple_(attempt.verified_at, attempt.id) < tuple_(boundary, before))
    rows = (await db.execute(query)).mappings().all()
    refunds = [RefundQueueEntry.model_validate(row) for row in rows[:limit]]
    return RefundQueue(
        refunds=refunds, next_before=refunds[-1].attempt_id if len(rows) > limit else None
    )
