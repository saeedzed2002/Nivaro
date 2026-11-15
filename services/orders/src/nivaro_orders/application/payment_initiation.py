from dataclasses import dataclass
from datetime import timedelta
from uuid import UUID, uuid5

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from nivaro_orders.application.reservations import db_time
from nivaro_orders.domain.checkout import CheckoutError, Contract, Version
from nivaro_orders.infrastructure.http_json import UpstreamUnavailable
from nivaro_orders.infrastructure.models import Order, OrderPaymentInitiation
from nivaro_orders.infrastructure.reservations import CatalogReservations, ReservationUnavailable
from nivaro_orders.infrastructure.simulator_payments import (
    PaymentBlocked,
    PaymentIntent,
    SimulatorPayments,
)

MINIMUM_HOLD = timedelta(seconds=90)


class StartPayment(Contract):
    order_version: Version


async def request_payment(
    db: AsyncSession,
    customer_id: UUID,
    order_id: UUID,
    version: int,
    key: str,
) -> None:
    async with db.begin():
        order = await db.scalar(
            select(Order)
            .where(Order.id == order_id, Order.customer_id == customer_id)
            .with_for_update()
        )
        if order is None:
            raise CheckoutError("checkout.not_found")
        if key != str(order.id):
            raise CheckoutError("checkout.invalid_idempotency_key")
        existing = await db.get(OrderPaymentInitiation, order.id)
        if existing is not None:
            if existing.order_version != version:
                raise CheckoutError("payment.order_changed")
            return
        if order.version != version:
            raise CheckoutError("payment.order_changed")
        now = await db_time(db)
        if (
            order.status != "awaiting_payment"
            or order.total_minor <= 0
            or order.reservation_expires_at is None
            or order.reservation_expires_at < now + MINIMUM_HOLD
        ):
            raise CheckoutError("payment.not_payable")
        db.add(
            OrderPaymentInitiation(
                order_id=order.id,
                order_version=order.version,
                attempt_id=uuid5(order.id, "customer-simulator-payment"),
                reservation_expires_at=order.reservation_expires_at,
                state="queued",
                retry_at=now,
            )
        )


@dataclass(frozen=True)
class PaymentWork:
    intent: PaymentIntent
    customer_id: UUID
    quote_id: UUID
    number: int
    can_start: bool


async def claim(db: AsyncSession) -> PaymentWork | None:
    async with db.begin():
        candidate = (
            await db.execute(
                select(Order, OrderPaymentInitiation)
                .join(OrderPaymentInitiation, OrderPaymentInitiation.order_id == Order.id)
                .where(OrderPaymentInitiation.retry_at <= func.statement_timestamp())
                .order_by(OrderPaymentInitiation.retry_at, OrderPaymentInitiation.order_id)
                .limit(1)
                .with_for_update(of=Order, skip_locked=True)
            )
        ).one_or_none()
        if candidate is None:
            return None
        order, initiation = candidate
        await db.refresh(initiation)
        now = await db_time(db)
        if initiation.retry_at is None or initiation.retry_at > now:
            return None
        initiation.attempts += 1
        initiation.retry_at = now + timedelta(seconds=60)
        return PaymentWork(
            PaymentIntent(
                initiation.attempt_id,
                order.id,
                initiation.order_version,
                order.market,
                order.currency,
                order.total_minor,
                initiation.reservation_expires_at,
            ),
            order.customer_id,
            order.quote_id,
            initiation.attempts,
            order.status == "awaiting_payment"
            and order.version == initiation.order_version
            and initiation.reservation_expires_at >= now + MINIMUM_HOLD,
        )


async def submit(
    work: PaymentWork, catalog: CatalogReservations, payments: SimulatorPayments
) -> None:
    intent = work.intent
    attempt = await payments.request_attempt(intent, "read") if work.number > 1 else None
    if attempt is None:
        if not work.can_start:
            raise PaymentBlocked()
        hold = await catalog.read_hold(intent.order_id, work.customer_id)
        if (
            hold is None
            or hold.state != "held"
            or (
                hold.operation_id,
                hold.quote_id,
                hold.customer_id,
                hold.market,
                hold.currency,
                hold.expires_at,
            )
            != (
                intent.order_id,
                work.quote_id,
                work.customer_id,
                intent.market,
                intent.currency,
                intent.reservation_expires_at,
            )
        ):
            raise PaymentBlocked()
        attempt = await payments.request_attempt(intent, "start")
    if attempt is None:
        raise UpstreamUnavailable()
    if attempt.verified_at is None:
        attempt = await payments.request_attempt(intent, "verify")
    if attempt is None:
        raise UpstreamUnavailable()
    if attempt.status == "failed":
        raise PaymentBlocked()


async def advance_customer_payment(
    sessions: async_sessionmaker[AsyncSession],
    catalog: CatalogReservations,
    payments: SimulatorPayments,
) -> bool:
    async with sessions() as db:
        work = await claim(db)
        if work is None:
            return False
        state = "submitted"
        try:
            await submit(work, catalog, payments)
        except PaymentBlocked:
            state = "blocked"
        except (ReservationUnavailable, UpstreamUnavailable):
            state = "queued"
        async with db.begin():
            row = await db.get(
                OrderPaymentInitiation,
                work.intent.order_id,
                with_for_update=True,
                populate_existing=True,
            )
            if row is not None and row.state == "queued" and row.attempts == work.number:
                row.state = state
                row.retry_at = (
                    await db_time(db) + timedelta(seconds=min(60, 2 ** min(work.number, 6)))
                    if state == "queued"
                    else None
                )
        return True
