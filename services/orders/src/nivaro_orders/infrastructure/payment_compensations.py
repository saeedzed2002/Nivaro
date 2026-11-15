from typing import Literal
from uuid import UUID

import httpx
from pydantic import AwareDatetime, Field

from nivaro_orders.domain.checkout import Contract, Currency
from nivaro_orders.infrastructure.checkout_sources import ErrorEnvelope, authorization, parse
from nivaro_orders.infrastructure.http_json import UpstreamUnavailable, request_json
from nivaro_orders.infrastructure.reservations import ServiceToken
from nivaro_orders.settings import Settings

REJECTIONS = frozenset(
    {
        "payment.not_found",
        "refund.capture_mismatch",
        "refund.currency_or_amount",
        "refund.idempotency_conflict",
        "refund.not_captured",
        "request.invalid",
    }
)


class RefundReceipt(Contract):
    id: UUID
    payment_id: UUID
    currency: Currency
    amount_minor: int = Field(strict=True, gt=0, le=9_000_000_000_000_010)
    provider_reference: str
    completed_at: AwareDatetime
    simulated: Literal[True]


class PaymentCompensations:
    def __init__(self, http: httpx.AsyncClient, settings: Settings, secret: str) -> None:
        self.http = http
        self.identity = str(settings.identity_url).rstrip("/")
        self.payments = str(settings.payments_url).rstrip("/")
        self.secret = secret

    async def refund_remaining(
        self,
        *,
        attempt_id: UUID,
        refund_id: UUID,
        order_id: UUID,
        currency: str,
        captured_minor: int,
        reason: str,
    ) -> str | None:
        status, body = await request_json(
            self.http,
            "POST",
            self.identity + "/internal/v1/service-tokens",
            json_body={"audience": "nivaro-payments", "scope": "payments.refund"},
            auth=("orders", self.secret),
        )
        if status != 200:
            raise UpstreamUnavailable()
        headers = authorization(parse(ServiceToken, body).access_token)
        headers["Idempotency-Key"] = f"compensation-{refund_id}"
        status, body = await request_json(
            self.http,
            "POST",
            self.payments + f"/internal/v1/payments/attempts/{attempt_id}/compensation",
            headers=headers,
            json_body={
                "id": str(refund_id),
                "order_id": str(order_id),
                "currency": currency,
                "captured_minor": captured_minor,
                "reason": reason,
            },
        )
        if status == 200:
            receipt = parse(RefundReceipt, body)
            if (receipt.id, receipt.payment_id, receipt.currency) == (
                refund_id,
                attempt_id,
                currency,
            ) and receipt.amount_minor <= captured_minor:
                return None
        elif status in {404, 409, 422}:
            code = parse(ErrorEnvelope, body).error.code
            if status == 409 and code == "refund.already_refunded":
                return None
            if code in REJECTIONS:
                return code
        raise UpstreamUnavailable()
