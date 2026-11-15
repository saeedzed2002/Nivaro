from dataclasses import dataclass
from datetime import timedelta
from typing import Protocol
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from nivaro_orders.application.checkout import require_coupon_capacity
from nivaro_orders.application.reservations import ATTEMPT_LEASE, db_time, record_order_transition
from nivaro_orders.domain.checkout import CheckoutError
from nivaro_orders.infrastructure.models import (
    Coupon,
    CouponClaim,
    Order,
    OrderPaymentAttempt,
    OrderPaymentRefund,
)
from nivaro_orders.infrastructure.reservations import (
    Receipt,
    ReservationRejected,
    ReservationUnavailable,
)


class PaidReservations(Protocol):
    async def commit_paid(self, operation_id: UUID, customer_id: UUID) -> Receipt: ...


@dataclass(frozen=True)
class StockCommit:
    order_id: UUID
    attempt_id: UUID
    customer_id: UUID
    number: int


async def refund_recorded(db: AsyncSession, attempt_id: UUID) -> bool:
    return (
        await db.scalar(
            select(OrderPaymentRefund.id)
            .where(OrderPaymentRefund.payment_attempt_id == attempt_id)
            .limit(1)
        )
        is not None
    )


async def secure_coupon(db: AsyncSession, order: Order) -> bool:
    claim = await db.get(CouponClaim, order.id)
    if claim is None:
        return True
    coupon = await db.get(Coupon, claim.coupon_id, with_for_update=True)
    assert coupon is not None
    now = await db_time(db)
    if claim.state != "held" or claim.expires_at <= now:
        if not coupon.enabled:
            return False
        try:
            await require_coupon_capacity(db, coupon, order.customer_id, now)
        except CheckoutError:
            return False
    claim.state = "finalizing"
    return True


def payment_review(db: AsyncSession, order: Order, reason: str) -> None:
    order.reservation_error = reason
    record_order_transition(db, order, "payment_review", reason)


async def settle_coupon(db: AsyncSession, order: Order, *, committed: bool) -> None:
    claim = await db.get(CouponClaim, order.id)
    if claim is not None:
        await db.get(Coupon, claim.coupon_id, with_for_update=True)
        claim.state = "consumed" if committed else "released"


async def prepare_payment(db: AsyncSession, order_id: UUID | None = None) -> bool:
    async with db.begin():
        query = (
            select(Order, OrderPaymentAttempt)
            .join(OrderPaymentAttempt, Order.id == OrderPaymentAttempt.order_id)
            .where(
                OrderPaymentAttempt.disposition.is_(None),
                OrderPaymentAttempt.captured_minor.is_not(None),
            )
            .order_by(OrderPaymentAttempt.verified_at, OrderPaymentAttempt.id)
            .limit(1)
            .with_for_update(of=Order, skip_locked=True)
        )
        if order_id is not None:
            query = query.where(Order.id == order_id)
        candidate = (await db.execute(query)).one_or_none()
        if candidate is None:
            return False
        order, attempt = candidate
        await db.refresh(attempt)
        if attempt.disposition is not None:
            return True
        if attempt.outcome == "payment.amount_mismatch":
            attempt.disposition = "payment.amount_mismatch"
        elif order.status == "cancelled":
            attempt.disposition = "payment.cancelled_order"
        elif order.status not in {"awaiting_payment", "expired"}:
            attempt.disposition = "payment.duplicate_capture"
        elif await refund_recorded(db, attempt.id):
            attempt.disposition = "payment.refund_already_recorded"
            payment_review(db, order, attempt.disposition)
        elif not await secure_coupon(db, order):
            attempt.disposition = "payment.coupon_quota_unavailable"
            payment_review(db, order, attempt.disposition)
        else:
            attempt.disposition = "selected"
            attempt.stock_retry_at = await db_time(db)
            order.reservation_error = None
            record_order_transition(db, order, "payment_processing", "payment.capture_verified")
        return True


async def claim_stock(db: AsyncSession, order_id: UUID | None) -> StockCommit | None:
    async with db.begin():
        query = (
            select(Order, OrderPaymentAttempt)
            .join(OrderPaymentAttempt, Order.id == OrderPaymentAttempt.order_id)
            .where(
                Order.status == "payment_processing",
                OrderPaymentAttempt.stock_retry_at <= await db_time(db),
            )
            .order_by(OrderPaymentAttempt.stock_retry_at, OrderPaymentAttempt.id)
            .limit(1)
            .with_for_update(of=Order, skip_locked=True)
        )
        if order_id is not None:
            query = query.where(Order.id == order_id)
        candidate = (await db.execute(query)).one_or_none()
        if candidate is None:
            return None
        order, attempt = candidate
        await db.refresh(attempt)
        now = await db_time(db)
        if attempt.stock_retry_at is None or attempt.stock_retry_at > now:
            return None
        if attempt.stock_attempts == 0 and await refund_recorded(db, attempt.id):
            attempt.stock_retry_at = None
            await settle_coupon(db, order, committed=False)
            payment_review(db, order, "payment.refund_already_recorded")
            return None
        attempt.stock_attempts += 1
        attempt.stock_retry_at = now + ATTEMPT_LEASE
        return StockCommit(order.id, attempt.id, order.customer_id, attempt.stock_attempts)


async def finish_stock(
    db: AsyncSession, commit: StockCommit, receipt: Receipt | None, reason: str | None
) -> None:
    async with db.begin():
        order = await db.get(Order, commit.order_id, with_for_update=True)
        attempt = await db.get(OrderPaymentAttempt, commit.attempt_id)
        assert order is not None and attempt is not None
        if order.status != "payment_processing" or attempt.stock_attempts != commit.number:
            return
        if receipt is not None and (
            receipt.operation_id,
            receipt.quote_id,
            receipt.customer_id,
            receipt.market,
            receipt.currency,
        ) == (order.id, order.quote_id, order.customer_id, order.market, order.currency):
            reason = {
                "expired": "payment.stock_unavailable",
                "released": "payment.stock_released",
            }.get(receipt.state)
        else:
            receipt = None
        committed = receipt is not None and receipt.state == "committed"
        if not committed and reason is None:
            attempt.stock_retry_at = await db_time(db) + timedelta(
                seconds=min(60, 2 ** min(commit.number, 6))
            )
            return
        attempt.stock_retry_at = None
        await settle_coupon(db, order, committed=committed)
        if reason is not None:
            payment_review(db, order, reason)
        elif await refund_recorded(db, attempt.id):
            payment_review(db, order, "payment.refund_already_recorded")
        else:
            record_order_transition(db, order, "paid", "payment.stock_committed")


async def advance_payment_stock(
    sessions: async_sessionmaker[AsyncSession],
    catalog: PaidReservations,
    order_id: UUID | None = None,
) -> bool:
    async with sessions() as db:
        commit = await claim_stock(db, order_id)
        if commit is None:
            return False
        receipt, reason = None, None
        try:
            receipt = await catalog.commit_paid(commit.order_id, commit.customer_id)
        except ReservationRejected as exc:
            reason = exc.code
        except ReservationUnavailable:
            pass
        await finish_stock(db, commit, receipt, reason)
        return True
