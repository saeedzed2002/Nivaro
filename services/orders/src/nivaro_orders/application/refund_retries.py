from uuid import UUID

from pydantic import AwareDatetime
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from nivaro_orders.application.payment_compensation import confirmed_refund_total
from nivaro_orders.application.reservations import db_time, record_order_transition
from nivaro_orders.domain.checkout import CheckoutError, Contract, Version
from nivaro_orders.infrastructure.models import (
    Order,
    OrderPaymentAttempt,
    OrderPaymentCompensation,
    OrderRefundRetry,
)


class RetryRefundCommand(Contract):
    expected_attempts: Version


class RefundRetryView(Contract):
    refund_id: UUID
    operation_id: UUID
    actor_id: UUID
    expected_attempts: Version
    previous_error: str | None
    queued_at: AwareDatetime


async def retry_refund(
    db: AsyncSession,
    refund_id: UUID,
    operation_id: UUID,
    actor_id: UUID,
    command: RetryRefundCommand,
) -> RefundRetryView:
    async with db.begin():
        order = await db.scalar(
            select(Order)
            .join(OrderPaymentAttempt, OrderPaymentAttempt.order_id == Order.id)
            .join(
                OrderPaymentCompensation,
                OrderPaymentCompensation.attempt_id == OrderPaymentAttempt.id,
            )
            .where(OrderPaymentCompensation.refund_id == refund_id)
            .with_for_update(of=Order)
        )
        if order is None:
            raise CheckoutError("refund.not_found")
        existing = await db.get(OrderRefundRetry, (refund_id, operation_id))
        if existing is not None:
            if (existing.actor_id, existing.expected_attempts) != (
                actor_id,
                command.expected_attempts,
            ):
                raise CheckoutError("refund.idempotency_conflict")
            return RefundRetryView.model_validate(existing, from_attributes=True)

        # Read the compensation after acquiring the shared order lock used by the worker and event consumer.
        refund = await db.scalar(
            select(OrderPaymentCompensation).where(OrderPaymentCompensation.refund_id == refund_id)
        )
        assert refund is not None
        if refund.state != "manual_review" or refund.attempts != command.expected_attempts:
            raise CheckoutError("refund.retry_conflict")
        if refund.closes_order and (
            order.status != "payment_review" or order.reservation_error != refund.last_error
        ):
            raise CheckoutError("refund.retry_conflict")
        if await confirmed_refund_total(db, refund.attempt_id) >= refund.captured_minor:
            raise CheckoutError("refund.retry_conflict")

        now = await db_time(db)
        refund.state = "pending"
        refund.retry_at = now
        if refund.closes_order:
            order.reservation_error = None
            record_order_transition(
                db, order, "refund_pending", "refund.staff_retry", staff_actor_id=actor_id
            )
        audit = OrderRefundRetry(
            refund_id=refund_id,
            operation_id=operation_id,
            actor_id=actor_id,
            expected_attempts=refund.attempts,
            previous_error=refund.last_error,
            queued_at=now,
        )
        db.add(audit)
        return RefundRetryView.model_validate(audit, from_attributes=True)
