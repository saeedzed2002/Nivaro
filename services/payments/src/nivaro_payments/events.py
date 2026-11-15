from datetime import datetime
from typing import Literal
from uuid import UUID, uuid4

from pydantic import AwareDatetime

from nivaro_payments.contracts import Contract, Currency, Market
from nivaro_payments.models import Attempt, OutboxEvent, Refund

type Outcome = Literal["payment.succeeded", "payment.failed", "payment.amount_mismatch"]


class PaymentDetails(Contract):
    order_id: UUID
    order_version: int
    payment_attempt_id: UUID
    market: Market
    currency: Currency
    amount_minor: int


class OutcomeDetails(PaymentDetails):
    captured_minor: int | None


class RefundDetails(PaymentDetails):
    refund_id: UUID


class Envelope(Contract):
    event_id: UUID
    schema_version: Literal[1] = 1
    occurred_at: AwareDatetime
    producer: Literal["payments"] = "payments"
    aggregate_id: UUID
    aggregate_version: int
    correlation_id: UUID
    causation_id: UUID | None = None


class AttemptOutcome(Envelope):
    event_type: Outcome
    payload: OutcomeDetails


class RefundCompleted(Envelope):
    event_type: Literal["payment.refund.completed"] = "payment.refund.completed"
    payload: RefundDetails


def outbox(event: AttemptOutcome | RefundCompleted) -> OutboxEvent:
    return OutboxEvent(
        id=event.event_id,
        event_type=event.event_type,
        aggregate_id=event.aggregate_id,
        aggregate_version=event.aggregate_version,
        created_at=event.occurred_at,
        envelope=event.model_dump(mode="json"),
    )


def outcome(row: Attempt, name: Outcome, now: datetime) -> OutboxEvent:
    return outbox(
        AttemptOutcome(
            event_id=uuid4(),
            event_type=name,
            occurred_at=now,
            aggregate_id=row.id,
            aggregate_version=row.version,
            correlation_id=row.order_id,
            payload=OutcomeDetails(
                order_id=row.order_id,
                order_version=row.order_version,
                payment_attempt_id=row.id,
                market=row.market,
                currency=row.currency,
                amount_minor=row.amount_minor,
                captured_minor=row.captured_minor,
            ),
        )
    )


def refund_completed(row: Attempt, refund: Refund) -> OutboxEvent:
    return outbox(
        RefundCompleted(
            event_id=uuid4(),
            occurred_at=refund.completed_at,
            aggregate_id=refund.id,
            aggregate_version=1,
            correlation_id=row.order_id,
            payload=RefundDetails(
                order_id=row.order_id,
                order_version=row.order_version,
                payment_attempt_id=row.id,
                market=row.market,
                currency=refund.currency,
                amount_minor=refund.amount_minor,
                refund_id=refund.id,
            ),
        )
    )
