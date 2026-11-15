import hashlib
import json
from datetime import datetime
from typing import Annotated, Literal, Self
from uuid import UUID

from pydantic import Field, model_validator

from nivaro_catalog.domain.contracts import (
    Contract,
    EvaluationRequest,
    Finding,
    MarketContext,
    MoneyAmount,
    Revision,
    Selection,
    Specifications,
    Status,
)

Version = Annotated[int, Field(strict=True, ge=1, le=2_147_483_647)]
Fingerprint = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
ReservationState = Literal["held", "committed", "released", "expired"]


class CheckoutError(Exception):
    def __init__(self, code: str, message: str, status: int = 409, *details: str) -> None:
        self.code, self.message, self.status, self.details = code, message, status, list(details)
        super().__init__(message)


class CartLine(Contract):
    id: UUID
    version: Version
    variant_id: UUID
    quantity: Annotated[int, Field(strict=True, ge=1, le=20)]
    group_id: UUID | None = None
    slot_key: Annotated[str, Field(pattern=r"^[a-z]+(:[1-9][0-9]?)?$", max_length=32)] | None = None


class CartGroup(Contract):
    id: UUID
    version: Version
    name: Annotated[str, Field(min_length=1, max_length=100)]
    mode: Literal["complete_build", "parts_only"]
    requires_dedicated_gpu: bool
    source_build_id: UUID | None = None
    source_build_version: Version | None = None

    @model_validator(mode="after")
    def validate_source(self) -> Self:
        if (self.source_build_id is None) != (self.source_build_version is None):
            raise ValueError("Build provenance requires both identifier and version")
        return self


class CartSnapshot(MarketContext):
    id: UUID
    version: Version
    lines: list[CartLine] = Field(min_length=1, max_length=100)
    groups: list[CartGroup] = Field(max_length=100)

    @model_validator(mode="after")
    def validate_snapshot(self) -> Self:
        group_ids = {group.id for group in self.groups}
        if len(group_ids) != len(self.groups) or len({line.id for line in self.lines}) != len(
            self.lines
        ):
            raise ValueError("Line and group identifiers must be unique")
        for line in self.lines:
            if line.group_id is None:
                if line.slot_key is not None:
                    raise ValueError("Standalone lines cannot have a slot")
            elif line.group_id not in group_ids or line.slot_key is None:
                raise ValueError("Grouped lines require an existing group and slot")
        for group in self.groups:
            self.evaluation_request(group)
        return self

    def evaluation_request(self, group: CartGroup) -> EvaluationRequest:
        return EvaluationRequest(
            market=self.market,
            currency=self.currency,
            mode=group.mode,
            requires_dedicated_gpu=group.requires_dedicated_gpu,
            selections=[
                Selection.model_validate(
                    {
                        "slot_key": line.slot_key,
                        "role": (line.slot_key or "").split(":")[0],
                        "variant_id": line.variant_id,
                        "quantity": line.quantity,
                    }
                )
                for line in sorted(self.lines, key=lambda line: line.slot_key or "")
                if line.group_id == group.id
            ],
        )

    def fingerprint(self) -> str:
        payload = self.model_dump(mode="json")
        for field in ("lines", "groups"):
            payload[field].sort(key=lambda item: item["id"])
        return hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()


class QuoteRequest(Contract):
    quote_id: UUID
    operation_id: UUID
    customer_id: UUID
    cart: CartSnapshot


class QuotedLine(CartLine):
    product_id: UUID
    product_name: str
    sku: str
    specifications: Specifications
    spec_version: Version
    unit_price_minor: MoneyAmount
    price_version: Version


class QuotedGroup(CartGroup, Revision):
    status: Status
    findings: list[Finding]
    evaluated_at: datetime


class Quote(MarketContext):
    id: UUID
    operation_id: UUID
    customer_id: UUID
    cart_id: UUID
    cart_version: Version
    cart_fingerprint: Fingerprint
    lines: list[QuotedLine]
    groups: list[QuotedGroup]
    subtotal_minor: int
    expires_at: datetime


class ReservationRequest(Contract):
    operation_id: UUID
    quote_id: UUID
    customer_id: UUID
    cart_fingerprint: Fingerprint


class Reservation(MarketContext):
    operation_id: UUID
    quote_id: UUID
    customer_id: UUID
    state: ReservationState
    expires_at: datetime
