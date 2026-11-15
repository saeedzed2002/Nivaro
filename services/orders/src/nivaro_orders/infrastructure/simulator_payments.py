from dataclasses import dataclass
from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

import httpx
from pydantic import AwareDatetime, Field

from nivaro_orders.domain.checkout import Contract, Market, MarketTerms
from nivaro_orders.infrastructure.checkout_sources import (
    ErrorEnvelope,
    SourceError,
    authorization,
    parse,
)
from nivaro_orders.infrastructure.http_json import UpstreamUnavailable, request_json
from nivaro_orders.infrastructure.reservations import ServiceToken
from nivaro_orders.settings import Settings


@dataclass(frozen=True)
class PaymentIntent:
    id: UUID
    order_id: UUID
    order_version: int
    market: str
    currency: str
    amount_minor: int
    reservation_expires_at: datetime


type AttemptStatus = Literal["pending", "ambiguous", "failed", "succeeded", "amount_mismatch"]


class AttemptReceipt(MarketTerms):
    id: UUID
    order_id: UUID
    order_version: int
    amount_minor: int
    captured_minor: int | None
    status: AttemptStatus
    version: int
    provider_reference: str
    verified_at: AwareDatetime | None
    simulated: Literal[True]


class OperationsAttempt(AttemptReceipt):
    created_at: AwareDatetime
    reconcile_at: AwareDatetime | None
    reconciliation_attempts: int


class OperationsPage(Contract):
    attempts: Annotated[list[OperationsAttempt], Field(max_length=50)]
    next_before: UUID | None


class PaymentBlocked(Exception):
    """The recorded simulator request cannot produce a payable attempt."""


class SimulatorPayments:
    def __init__(self, http: httpx.AsyncClient, settings: Settings, secret: str) -> None:
        self.http = http
        self.identity = str(settings.identity_url).rstrip("/")
        self.attempts = str(settings.payments_url).rstrip("/") + "/internal/v1/payments/attempts"
        self.operations = (
            str(settings.payments_url).rstrip("/") + "/internal/v1/payments/operations/attempts"
        )
        self.secret = secret

    async def headers(
        self, operation: Literal["read", "start", "verify", "operations.read"]
    ) -> dict[str, str]:
        status, body = await request_json(
            self.http,
            "POST",
            self.identity + "/internal/v1/service-tokens",
            json_body={"audience": "nivaro-payments", "scope": f"payments.{operation}"},
            auth=("orders", self.secret),
        )
        if status != 200:
            raise UpstreamUnavailable()
        return authorization(parse(ServiceToken, body).access_token)

    async def list_operations(
        self,
        status: AttemptStatus | None,
        market: Market | None,
        order_id: UUID | None,
        before: UUID | None,
        limit: int,
    ) -> OperationsPage:
        query = {
            "status": status,
            "market": market,
            "order_id": order_id,
            "before": before,
            "limit": limit,
        }
        response_status, body = await request_json(
            self.http,
            "GET",
            self.operations,
            headers=await self.headers("operations.read"),
            params={key: str(value) for key, value in query.items() if value is not None},
            max_bytes=65536,
        )
        if response_status == 404 and parse(ErrorEnvelope, body).error.code == "payment.not_found":
            raise SourceError("payments.cursor_not_found", 404)
        if response_status != 200:
            raise UpstreamUnavailable()
        return parse(OperationsPage, body)

    async def read_operation(self, attempt_id: UUID) -> OperationsAttempt:
        status, body = await request_json(
            self.http,
            "GET",
            f"{self.operations}/{attempt_id}",
            headers=await self.headers("operations.read"),
        )
        if status == 404 and parse(ErrorEnvelope, body).error.code == "payment.not_found":
            raise SourceError("payment.not_found", 404)
        if status != 200:
            raise UpstreamUnavailable()
        attempt = parse(OperationsAttempt, body)
        if attempt.id != attempt_id:
            raise UpstreamUnavailable()
        return attempt

    async def request_attempt(
        self,
        intent: PaymentIntent,
        operation: Literal["read", "start", "verify"],
    ) -> AttemptReceipt | None:
        headers = await self.headers(operation)
        if operation == "start":
            headers["Idempotency-Key"] = f"customer-payment-{intent.id}"
            status, body = await request_json(
                self.http,
                "POST",
                self.attempts,
                headers=headers,
                json_body={
                    "id": str(intent.id),
                    "order_id": str(intent.order_id),
                    "order_version": intent.order_version,
                    "market": intent.market,
                    "currency": intent.currency,
                    "amount_minor": intent.amount_minor,
                    "reservation_expires_at": intent.reservation_expires_at.isoformat(),
                    "scenario": "success",
                },
            )
        else:
            path = self.attempts + f"/{intent.id}"
            status, body = await request_json(
                self.http,
                "GET" if operation == "read" else "POST",
                path if operation == "read" else path + "/verify",
                headers=headers,
            )
        if (
            status == 404
            and operation == "read"
            and parse(ErrorEnvelope, body).error.code == "payment.not_found"
        ):
            return None
        if (
            status == 409
            and operation == "start"
            and parse(ErrorEnvelope, body).error.code == "payment.reservation_too_short"
        ):
            raise PaymentBlocked()
        if status != 200:
            raise UpstreamUnavailable()
        receipt = parse(AttemptReceipt, body)
        if (
            receipt.id,
            receipt.order_id,
            receipt.order_version,
            receipt.market,
            receipt.currency,
            receipt.amount_minor,
        ) != (
            intent.id,
            intent.order_id,
            intent.order_version,
            intent.market,
            intent.currency,
            intent.amount_minor,
        ):
            raise UpstreamUnavailable()
        return receipt
