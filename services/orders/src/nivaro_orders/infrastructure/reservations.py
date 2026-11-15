from typing import Literal
from uuid import UUID

import httpx
from pydantic import AwareDatetime, ValidationError

from nivaro_orders.domain.checkout import Contract, MarketTerms
from nivaro_orders.infrastructure.http_json import UpstreamUnavailable, request_json
from nivaro_orders.settings import Settings

REJECTIONS = frozenset(
    {
        "build.selection_changed",
        "build.validation_stale",
        "inventory.insufficient_stock",
        "quote.eligibility_changed",
        "quote.expired",
        "quote.price_changed",
    }
)


class Receipt(MarketTerms):
    operation_id: UUID
    quote_id: UUID
    customer_id: UUID
    state: Literal["held", "committed", "released", "expired"]
    expires_at: AwareDatetime


class ReservationUnavailable(Exception):
    """A response does not prove whether catalog has made a reservation."""


class ReservationRejected(Exception):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


class ServiceToken(Contract):
    access_token: str


class CatalogError(Contract):
    code: str
    message: str
    details: list[str]
    request_id: str


class ErrorEnvelope(Contract):
    error: CatalogError


class CatalogReservations:
    def __init__(self, http: httpx.AsyncClient, settings: Settings, client_secret: str) -> None:
        self.http = http
        self.identity = str(settings.identity_url).rstrip("/")
        self.catalog = str(settings.catalog_url).rstrip("/")
        self.secret = client_secret

    async def recover_or_reserve(
        self, operation_id: UUID, quote_id: UUID, customer_id: UUID, cart_fingerprint: str
    ) -> Receipt:
        try:
            status, body = await request_json(
                self.http,
                "POST",
                self.identity + "/internal/v1/service-tokens",
                json_body={"audience": "nivaro-catalog", "scope": "catalog.reserve"},
                auth=("orders", self.secret),
            )
            if status != 200:
                raise ReservationUnavailable()
            token = ServiceToken.model_validate(body).access_token
            if not 1 <= len(token) <= 8192:
                raise ReservationUnavailable()
            headers = {"Authorization": f"Bearer {token}"}
            root = self.catalog + "/internal/v1/catalog/reservations"
            status, body = await request_json(
                self.http,
                "GET",
                root + f"/{operation_id}",
                headers=headers,
                params={"customer_id": str(customer_id)},
            )
            if (
                status == 404
                and ErrorEnvelope.model_validate(body).error.code == "reservation.not_found"
            ):
                status, body = await request_json(
                    self.http,
                    "POST",
                    root,
                    headers=headers,
                    json_body={
                        "operation_id": str(operation_id),
                        "customer_id": str(customer_id),
                        "quote_id": str(quote_id),
                        "cart_fingerprint": cart_fingerprint,
                    },
                )
                if status == 409:
                    code = ErrorEnvelope.model_validate(body).error.code
                    if code in REJECTIONS:
                        raise ReservationRejected(code)
            if status != 200:
                raise ReservationUnavailable()
            receipt = Receipt.model_validate(body)
            if (receipt.operation_id, receipt.quote_id, receipt.customer_id) != (
                operation_id,
                quote_id,
                customer_id,
            ):
                raise ReservationUnavailable()
            return receipt
        except (UpstreamUnavailable, ValidationError) as exc:
            raise ReservationUnavailable() from exc
