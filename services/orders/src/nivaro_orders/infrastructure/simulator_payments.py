from dataclasses import dataclass
from datetime import datetime
from typing import Literal
from uuid import UUID

import httpx
from pydantic import AwareDatetime

from nivaro_orders.domain.checkout import MarketTerms
from nivaro_orders.infrastructure.checkout_sources import ErrorEnvelope, authorization, parse
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


class AttemptReceipt(MarketTerms):
    id: UUID
    order_id: UUID
    order_version: int
    amount_minor: int
    captured_minor: int | None
    status: Literal["pending", "ambiguous", "failed", "succeeded", "amount_mismatch"]
    version: int
    provider_reference: str
    verified_at: AwareDatetime | None
    simulated: Literal[True]


class PaymentBlocked(Exception):
    """The recorded simulator request cannot produce a payable attempt."""


class SimulatorPayments:
    def __init__(self, http: httpx.AsyncClient, settings: Settings, secret: str) -> None:
        self.http = http
        self.identity = str(settings.identity_url).rstrip("/")
        self.attempts = str(settings.payments_url).rstrip("/") + "/internal/v1/payments/attempts"
        self.secret = secret

    async def request_attempt(
        self,
        intent: PaymentIntent,
        operation: Literal["read", "start", "verify"],
    ) -> AttemptReceipt | None:
        status, body = await request_json(
            self.http,
            "POST",
            self.identity + "/internal/v1/service-tokens",
            json_body={"audience": "nivaro-payments", "scope": f"payments.{operation}"},
            auth=("orders", self.secret),
        )
        if status != 200:
            raise UpstreamUnavailable()
        headers = authorization(parse(ServiceToken, body).access_token)
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
