from typing import Annotated, Literal, Self
from uuid import UUID

from pydantic import AwareDatetime, Field, TypeAdapter, model_validator

from nivaro_orders.domain.checkout import Contract, MarketTerms, Version

EXPIRED_RESERVATION_QUEUE = "orders.inventory.reservation.expired.v1"
PAYMENT_RESULTS_QUEUE = "orders.payment.results.v1"


class ExpiryPayload(MarketTerms):
    quote_id: UUID
    expires_at: AwareDatetime


class ExpiredReservation(Contract):
    event_id: UUID
    event_type: Literal["inventory.reservation.expired"]
    schema_version: Literal[1]
    occurred_at: AwareDatetime
    producer: Literal["catalog"]
    aggregate_id: UUID
    aggregate_version: Version
    correlation_id: UUID
    causation_id: UUID | None
    payload: ExpiryPayload

    @model_validator(mode="after")
    def validate_deadline_and_operation(self) -> Self:
        if self.aggregate_id != self.correlation_id or self.occurred_at < self.payload.expires_at:
            raise ValueError("Expiry must follow its deadline and identify the checkout operation")
        return self


PaymentAmount = Annotated[int, Field(strict=True, gt=0, le=9_000_000_000_000_000)]
CapturedAmount = Annotated[int, Field(strict=True, gt=0, le=9_000_000_000_000_010)]


class PaymentPayload(MarketTerms):
    order_id: UUID
    order_version: Version
    payment_attempt_id: UUID
    amount_minor: PaymentAmount

    @model_validator(mode="after")
    def validate_amount(self) -> Self:
        if self.currency == "IRR" and self.amount_minor % 10:
            raise ValueError("IRR amounts must be in whole tomans")
        return self


class PaymentOutcomePayload(PaymentPayload):
    captured_minor: CapturedAmount | None


class RefundPayload(PaymentPayload):
    refund_id: UUID
    amount_minor: CapturedAmount


class PaymentEnvelope(Contract):
    event_id: UUID
    schema_version: Literal[1]
    occurred_at: AwareDatetime
    producer: Literal["payments"]
    aggregate_id: UUID
    aggregate_version: Version
    correlation_id: UUID
    causation_id: UUID | None


class PaymentOutcome(PaymentEnvelope):
    event_type: Literal["payment.succeeded", "payment.failed", "payment.amount_mismatch"]
    payload: PaymentOutcomePayload

    @model_validator(mode="after")
    def validate_outcome(self) -> Self:
        payload = self.payload
        if (self.aggregate_id, self.correlation_id) != (
            payload.payment_attempt_id,
            payload.order_id,
        ):
            raise ValueError("Outcome identifiers must match the attempt and order")
        captured = payload.captured_minor
        if captured is None:
            expected = "payment.failed"
        else:
            if payload.currency == "IRR" and captured % 10:
                raise ValueError("IRR captures must be in whole tomans")
            expected = (
                "payment.succeeded"
                if captured == payload.amount_minor
                else "payment.amount_mismatch"
            )
        if self.event_type != expected:
            raise ValueError("Outcome must match the reported capture")
        return self


class PaymentRefund(PaymentEnvelope):
    event_type: Literal["payment.refund.completed"]
    payload: RefundPayload

    @model_validator(mode="after")
    def validate_refund(self) -> Self:
        if (self.aggregate_id, self.correlation_id, self.aggregate_version) != (
            self.payload.refund_id,
            self.payload.order_id,
            1,
        ):
            raise ValueError("Refund identifiers and version must match the event")
        return self


PaymentResult = Annotated[PaymentOutcome | PaymentRefund, Field(discriminator="event_type")]
payment_result_adapter: TypeAdapter[PaymentResult] = TypeAdapter(PaymentResult)
