from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Protocol
from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from nivaro_orders.infrastructure.models import (
    CheckoutOperation,
    Coupon,
    CouponClaim,
    Order,
    OrderTransition,
)
from nivaro_orders.infrastructure.reservations import (
    Receipt,
    ReservationRejected,
    ReservationUnavailable,
)

ATTEMPT_LEASE = timedelta(seconds=30)


class Reservations(Protocol):
    async def recover_or_reserve(
        self, operation_id: UUID, quote_id: UUID, customer_id: UUID, cart_fingerprint: str
    ) -> Receipt: ...


@dataclass(frozen=True)
class Attempt:
    order_id: UUID
    quote_id: UUID
    customer_id: UUID
    cart_fingerprint: str
    number: int


async def db_time(db: AsyncSession) -> datetime:
    value: datetime = (await db.execute(select(func.clock_timestamp()))).scalar_one()
    return value


async def claim_attempt(db: AsyncSession, order_id: UUID | None) -> Attempt | None:
    async with db.begin():
        query = (
            select(Order)
            .where(
                Order.status == "pending_reservation",
                or_(
                    Order.reservation_retry_at.is_(None),
                    Order.reservation_retry_at <= func.statement_timestamp(),
                ),
            )
            .order_by(Order.reservation_retry_at.nulls_first(), Order.created_at, Order.id)
            .limit(1)
            .with_for_update(skip_locked=True)
        )
        if order_id is not None:
            query = query.where(Order.id == order_id)
        order = await db.scalar(query)
        if order is None:
            return None
        order.reservation_attempts += 1
        order.reservation_retry_at = await db_time(db) + ATTEMPT_LEASE
        return Attempt(
            order.id,
            order.quote_id,
            order.customer_id,
            order.cart_fingerprint,
            order.reservation_attempts,
        )


async def transition(
    db: AsyncSession, order: Order, status: str, reason: str, expires_at: datetime | None
) -> None:
    operation = await db.get(CheckoutOperation, order.id, with_for_update=True)
    assert operation is not None
    claim = await db.get(CouponClaim, order.id)
    if claim is not None:
        # Checkout claim writers lock the same parent coupon before measuring quota.
        await db.get(Coupon, claim.coupon_id, with_for_update=True)
    if status == "awaiting_payment":
        assert expires_at is not None
        if expires_at <= await db_time(db):
            status, reason = "expired", "reservation.expired"

    record_order_transition(db, order, status, reason)
    order.reservation_expires_at = expires_at
    order.reservation_retry_at = None
    order.reservation_error = None if status == "awaiting_payment" else reason

    operation.state = (
        "reservation_confirmed" if status == "awaiting_payment" else "reservation_failed"
    )
    if claim is not None:
        if status == "awaiting_payment":
            assert expires_at is not None
            claim.expires_at = expires_at
        elif claim.state == "held":
            claim.state = "released"


def record_order_transition(db: AsyncSession, order: Order, status: str, reason: str) -> None:
    order.status = status
    order.version += 1
    db.add(
        OrderTransition(
            order_id=order.id,
            version=order.version,
            customer_id=order.customer_id,
            status=status,
            reason=reason,
        )
    )


async def apply_outcome(
    db: AsyncSession, attempt: Attempt, receipt: Receipt | None, code: str | None
) -> None:
    async with db.begin():
        order = await db.get(Order, attempt.order_id, with_for_update=True)
        assert order is not None
        # The lease can lapse if a process stalls. Only the current attempt writes.
        if order.status != "pending_reservation" or order.reservation_attempts != attempt.number:
            return
        now = await db_time(db)
        if code is not None:
            status = "expired" if code == "quote.expired" else "cancelled"
            await transition(db, order, status, code, None)
        elif (
            receipt is None
            or receipt.state == "committed"
            or (receipt.market, receipt.currency) != (order.market, order.currency)
        ):
            order.reservation_retry_at = now + timedelta(
                seconds=min(60, 2 ** min(attempt.number, 6))
            )
            order.reservation_error = "reservation.unavailable"
        elif receipt.state == "released":
            await transition(db, order, "cancelled", "reservation.released", receipt.expires_at)
        elif receipt.state == "expired" or receipt.expires_at <= now:
            await transition(db, order, "expired", "reservation.expired", receipt.expires_at)
        else:
            await transition(db, order, "awaiting_payment", "reservation.held", receipt.expires_at)


async def advance_reservation(
    sessions: async_sessionmaker[AsyncSession], catalog: Reservations, order_id: UUID | None = None
) -> bool:
    async with sessions() as db:
        attempt = await claim_attempt(db, order_id)
        if attempt is None:
            return False
        receipt = None
        rejection = None
        # The claim transaction has committed. Catalog's operation ID survives retries.
        try:
            receipt = await catalog.recover_or_reserve(
                attempt.order_id, attempt.quote_id, attempt.customer_id, attempt.cart_fingerprint
            )
        except ReservationRejected as exc:
            rejection = exc.code
        except ReservationUnavailable:
            pass
        await apply_outcome(db, attempt, receipt, rejection)
        return True


async def expire_unpaid(db: AsyncSession) -> bool:
    async with db.begin():
        order = await db.scalar(
            select(Order)
            .where(
                Order.status == "awaiting_payment",
                Order.reservation_expires_at <= func.statement_timestamp(),
            )
            .order_by(Order.reservation_expires_at, Order.id)
            .limit(1)
            .with_for_update(skip_locked=True)
        )
        if order is None:
            return False
        await transition(db, order, "expired", "reservation.expired", order.reservation_expires_at)
        return True
