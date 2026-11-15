from typing import Literal, Self
from uuid import UUID

from pydantic import AwareDatetime, model_validator

from nivaro_orders.domain.checkout import Contract, MarketTerms, Version

EXPIRED_RESERVATION_QUEUE = "orders.inventory.reservation.expired.v1"


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
