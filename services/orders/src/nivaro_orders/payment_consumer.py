import asyncio
import logging

from aio_pika.abc import AbstractIncomingMessage
from pydantic import ValidationError
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from nivaro_orders.application.payment_compensation import confirm_compensation
from nivaro_orders.domain.events import (
    PAYMENT_RESULTS_QUEUE,
    PaymentOutcome,
    PaymentRefund,
    PaymentResult,
    payment_result_adapter,
)
from nivaro_orders.event_subscription import subscribe
from nivaro_orders.infrastructure.database import Database
from nivaro_orders.infrastructure.models import (
    InboxEvent,
    Order,
    OrderPaymentAttempt,
    OrderPaymentRefund,
    OrderTransition,
)

log = logging.getLogger(__name__)


class PaymentResultRejected(Exception):
    """The event conflicts with the immutable order or financial evidence."""


async def record_refund(db: AsyncSession, event: PaymentRefund) -> None:
    payload = event.payload
    inserted = await db.scalar(
        insert(OrderPaymentRefund)
        .values(
            id=payload.refund_id,
            payment_attempt_id=payload.payment_attempt_id,
            amount_minor=payload.amount_minor,
            completed_at=event.occurred_at,
        )
        .on_conflict_do_nothing(index_elements=[OrderPaymentRefund.id])
        .returning(OrderPaymentRefund.id)
    )
    if inserted is None:
        refund = await db.get(OrderPaymentRefund, payload.refund_id)
        assert refund is not None
        if (refund.payment_attempt_id, refund.amount_minor, refund.completed_at) != (
            payload.payment_attempt_id,
            payload.amount_minor,
            event.occurred_at,
        ):
            raise PaymentResultRejected("refund.evidence_conflict")


def record_outcome(attempt: OrderPaymentAttempt, event: PaymentOutcome) -> None:
    evidence = (
        event.event_type,
        event.aggregate_version,
        event.payload.captured_minor,
        event.occurred_at,
    )
    if attempt.outcome is None:
        attempt.outcome, attempt.aggregate_version, attempt.captured_minor, attempt.verified_at = (
            evidence
        )
    elif (
        attempt.outcome,
        attempt.aggregate_version,
        attempt.captured_minor,
        attempt.verified_at,
    ) != evidence:
        raise PaymentResultRejected("payment.evidence_conflict")


async def apply_payment_result(db: AsyncSession, event: PaymentResult) -> None:
    payload = event.payload
    async with db.begin():
        inserted = await db.scalar(
            insert(InboxEvent)
            .values(
                consumer_name=PAYMENT_RESULTS_QUEUE,
                event_id=event.event_id,
                aggregate_id=event.aggregate_id,
                aggregate_version=event.aggregate_version,
            )
            .on_conflict_do_nothing()
            .returning(InboxEvent.event_id)
        )
        if inserted is None:
            return
        order = await db.get(Order, payload.order_id, with_for_update=True)
        if order is None or (order.market, order.currency) != (payload.market, payload.currency):
            raise PaymentResultRejected("payment.order_terms_mismatch")
        payable = await db.get(OrderTransition, (order.id, payload.order_version))
        if payable is None or payable.status != "awaiting_payment":
            raise PaymentResultRejected("payment.order_version_not_payable")
        if isinstance(event, PaymentOutcome) and event.payload.amount_minor != order.total_minor:
            raise PaymentResultRejected("payment.order_amount_mismatch")

        # A refund can arrive first. Both results bind the same attempt to the reviewed order revision.
        await db.execute(
            insert(OrderPaymentAttempt)
            .values(
                id=payload.payment_attempt_id,
                order_id=order.id,
                order_version=payload.order_version,
            )
            .on_conflict_do_nothing(index_elements=[OrderPaymentAttempt.id])
        )
        attempt = await db.get(
            OrderPaymentAttempt, payload.payment_attempt_id, with_for_update=True
        )
        assert attempt is not None
        if (attempt.order_id, attempt.order_version) != (order.id, payload.order_version):
            raise PaymentResultRejected("payment.attempt_binding_conflict")
        if isinstance(event, PaymentRefund):
            await record_refund(db, event)
            await confirm_compensation(db, order, attempt.id)
        else:
            record_outcome(attempt, event)


async def consume(message: AbstractIncomingMessage, database: Database) -> None:
    if message.content_type != "application/json" or len(message.body) > 16384:
        await message.reject(requeue=False)
        return
    try:
        event = payment_result_adapter.validate_json(message.body)
    except ValidationError:
        log.warning("Rejected malformed payment result")
        await message.reject(requeue=False)
        return
    if (message.message_id, message.routing_key) != (str(event.event_id), event.event_type):
        log.warning("Rejected mismatched payment message metadata event_id=%s", event.event_id)
        await message.reject(requeue=False)
        return
    try:
        async with database.sessions() as db:
            await apply_payment_result(db, event)
    except PaymentResultRejected as exc:
        log.warning("Rejected payment result event_id=%s reason=%s", event.event_id, exc)
        await message.reject(requeue=False)
        return
    except SQLAlchemyError:
        count = message.headers.get("x-delivery-count", 0)
        attempt = min(max(count, 0), 4) if type(count) is int else 0
        log.warning("Payment result transaction will be retried event_id=%s", event.event_id)
        await asyncio.sleep(min(10, 2**attempt))
        await message.nack(requeue=True)
        return
    await message.ack()


if __name__ == "__main__":
    asyncio.run(subscribe(PAYMENT_RESULTS_QUEUE, consume))
