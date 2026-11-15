from typing import Annotated, Literal, Self
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

type Market = Literal["ir", "international"]
type Currency = Literal["IRR", "USD"]
type Scenario = Literal[
    "success", "failure", "ambiguous", "duplicate", "delay", "overpayment", "unavailable"
]
type AttemptState = Literal["pending", "ambiguous", "failed", "succeeded", "amount_mismatch"]
Amount = Annotated[int, Field(strict=True, gt=0, le=9_000_000_000_000_000)]
CapturedAmount = Annotated[int, Field(strict=True, gt=0, le=9_000_000_000_000_010)]
OperationKey = Annotated[str, Field(pattern=r"^[A-Za-z0-9._-]{1,128}$")]
RefundReason = Annotated[str, Field(pattern=r"^[a-z][a-z0-9_.-]{0,79}$")]


class PaymentError(Exception):
    def __init__(self, code: str, status: int = 409) -> None:
        self.code, self.status = code, status
        super().__init__(code)


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, from_attributes=True)


class PaymentIntent(Contract):
    id: UUID
    order_id: UUID
    order_version: Annotated[int, Field(strict=True, ge=1, le=2_147_483_647)]
    market: Market
    currency: Currency
    amount_minor: Amount
    reservation_expires_at: AwareDatetime
    scenario: Scenario = "success"

    @model_validator(mode="after")
    def validate_market_amount(self) -> Self:
        if (self.market == "ir") != (self.currency == "IRR"):
            raise ValueError("Payment currency must match the order market")
        if self.currency == "IRR" and self.amount_minor % 10:
            raise ValueError("IRR payments must be in whole tomans")
        return self


class AttemptView(Contract):
    id: UUID
    order_id: UUID
    order_version: int
    market: Market
    currency: Currency
    amount_minor: int
    captured_minor: int | None
    status: AttemptState
    version: int
    provider_reference: str
    verified_at: AwareDatetime | None
    simulated: Literal[True] = True


class RefundIntent(Contract):
    id: UUID
    currency: Currency
    amount_minor: CapturedAmount
    reason: RefundReason


class CompensationIntent(Contract):
    id: UUID
    order_id: UUID
    currency: Currency
    captured_minor: CapturedAmount
    reason: RefundReason


class RefundView(Contract):
    id: UUID
    payment_id: UUID
    currency: Currency
    amount_minor: int
    provider_reference: str
    completed_at: AwareDatetime
    simulated: Literal[True] = True
