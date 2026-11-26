from dataclasses import dataclass
from datetime import timedelta
from uuid import UUID, uuid4

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from nivaro_orders.application.reservations import ATTEMPT_LEASE, db_time, record_order_transition
from nivaro_orders.infrastructure.http_json import UpstreamUnavailable
from nivaro_orders.infrastructure.models import (
    Order,
    OrderPaymentAttempt,
    OrderPaymentCompensation,
    OrderPaymentRefund,
)
from nivaro_orders.infrastructure.payment_compensations import PaymentCompensations

ATTEMPT_REFUNDS = (
    "payment.amount_mismatch",
    "payment.duplicate_capture",
    "payment.cancelled_order",
)
ORDER_REFUNDS = ("payment.stock_unavailable", "payment.stock_released", "reservation.not_found")


@dataclass(frozen=True)
class RefundWork:
    attempt_id: UUID
    refund_id: UUID
    order_id: UUID
    currency: str
    captured_minor: int
    reason: str
    number: int


async def confirmed_refund_total(db: AsyncSession, attempt_id: UUID) -> int:
    total = await db.scalar(
        select(func.sum(OrderPaymentRefund.amount_minor)).where(
            OrderPaymentRefund.payment_attempt_id == attempt_id
        )
    )
    return int(total or 0)


async def confirm_compensation(db: AsyncSession, order: Order, attempt_id: UUID) -> None:
    compensation = await db.get(OrderPaymentCompensation, attempt_id)
    if compensation is None or compensation.state == "completed":
        return
    refunded = await confirmed_refund_total(db, attempt_id)
    if refunded != compensation.captured_minor:
        return
    compensation.state = "completed"
    compensation.retry_at = None
    compensation.last_error = None
    if compensation.closes_order and order.status in {"refund_pending", "payment_review"}:
        order.reservation_error = None
        record_order_transition(db, order, "refunded", "refund.confirmed")


async def schedule_compensation(db: AsyncSession, order_id: UUID | None = None) -> bool:
    async with db.begin():
        attempt = OrderPaymentAttempt
        query = (
            select(Order, attempt)
            .join(attempt, attempt.order_id == Order.id)
            .outerjoin(OrderPaymentCompensation, OrderPaymentCompensation.attempt_id == attempt.id)
            .where(
                OrderPaymentCompensation.attempt_id.is_(None),
                attempt.captured_minor.is_not(None),
                or_(
                    attempt.disposition.in_(ATTEMPT_REFUNDS),
                    and_(
                        Order.status == "payment_review",
                        or_(
                            attempt.disposition.in_(
                                (
                                    "payment.coupon_quota_unavailable",
                                    "payment.refund_already_recorded",
                                )
                            ),
                            and_(
                                attempt.disposition == "selected",
                                or_(
                                    Order.reservation_error.in_(ORDER_REFUNDS),
                                    and_(
                                        attempt.stock_attempts == 0,
                                        Order.reservation_error
                                        == "payment.refund_already_recorded",
                                    ),
                                ),
                            ),
                        ),
                    ),
                ),
            )
            .order_by(attempt.verified_at, attempt.id)
            .limit(1)
            .with_for_update(of=Order, skip_locked=True)
        )
        if order_id is not None:
            query = query.where(Order.id == order_id)
        candidate = (await db.execute(query)).one_or_none()
        if candidate is None:
            return False
        order, payment = candidate
        # Another worker may have inserted a row immediately before this order lock was acquired.
        if await db.get(OrderPaymentCompensation, payment.id) is not None:
            return True
        assert payment.captured_minor is not None and payment.disposition is not None
        reason = (
            order.reservation_error if payment.disposition == "selected" else payment.disposition
        )
        assert reason is not None
        closes_order = payment.disposition not in ATTEMPT_REFUNDS
        db.add(
            OrderPaymentCompensation(
                attempt_id=payment.id,
                refund_id=uuid4(),
                captured_minor=payment.captured_minor,
                closes_order=closes_order,
                reason=reason,
                state="pending",
                retry_at=await db_time(db),
            )
        )
        if closes_order:
            record_order_transition(db, order, "refund_pending", "refund.requested")
        await db.flush()
        await confirm_compensation(db, order, payment.id)
        return True


async def claim_refund(db: AsyncSession, order_id: UUID | None) -> RefundWork | None:
    async with db.begin():
        query = (
            select(Order, OrderPaymentCompensation)
            .join(OrderPaymentAttempt, OrderPaymentAttempt.order_id == Order.id)
            .join(
                OrderPaymentCompensation,
                OrderPaymentCompensation.attempt_id == OrderPaymentAttempt.id,
            )
            .where(OrderPaymentCompensation.retry_at <= func.statement_timestamp())
            .order_by(OrderPaymentCompensation.retry_at, OrderPaymentCompensation.attempt_id)
            .limit(1)
            .with_for_update(of=Order, skip_locked=True)
        )
        if order_id is not None:
            query = query.where(Order.id == order_id)
        candidate = (await db.execute(query)).one_or_none()
        if candidate is None:
            return None
        order, compensation = candidate
        await db.refresh(compensation)
        now = await db_time(db)
        if compensation.retry_at is None or compensation.retry_at > now:
            return None
        compensation.attempts += 1
        compensation.retry_at = now + ATTEMPT_LEASE
        return RefundWork(
            compensation.attempt_id,
            compensation.refund_id,
            order.id,
            order.currency,
            compensation.captured_minor,
            compensation.reason,
            compensation.attempts,
        )


async def finish_refund(
    db: AsyncSession, work: RefundWork, *, accepted: bool, error: str | None
) -> None:
    async with db.begin():
        order = await db.get(Order, work.order_id, with_for_update=True)
        compensation = await db.get(OrderPaymentCompensation, work.attempt_id)
        assert order is not None and compensation is not None
        if compensation.state != "pending" or compensation.attempts != work.number:
            return
        compensation.last_error = error
        if accepted:
            compensation.state = "awaiting_evidence"
            compensation.retry_at = None
        elif error is not None:
            compensation.state = "manual_review"
            compensation.retry_at = None
            if compensation.closes_order and order.status == "refund_pending":
                order.reservation_error = error
                record_order_transition(db, order, "payment_review", error)
        else:
            compensation.retry_at = await db_time(db) + timedelta(
                seconds=min(60, 2 ** min(work.number, 6))
            )


async def advance_refund(
    sessions: async_sessionmaker[AsyncSession],
    payments: PaymentCompensations,
    order_id: UUID | None = None,
) -> bool:
    async with sessions() as db:
        work = await claim_refund(db, order_id)
        if work is None:
            return False
        try:
            error = await payments.refund_remaining(
                attempt_id=work.attempt_id,
                refund_id=work.refund_id,
                order_id=work.order_id,
                currency=work.currency,
                captured_minor=work.captured_minor,
                reason=work.reason,
            )
        except UpstreamUnavailable:
            await finish_refund(db, work, accepted=False, error=None)
        else:
            await finish_refund(db, work, accepted=error is None, error=error)
        return True
