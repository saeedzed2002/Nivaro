import asyncio
from typing import Literal
from uuid import UUID

import httpx
from pydantic import BaseModel, ValidationError

from nivaro_orders.domain.checkout import (
    AddressSnapshot,
    CartSnapshot,
    CatalogQuote,
    CheckoutError,
    CheckoutIntent,
    Contract,
)
from nivaro_orders.infrastructure.http_json import UpstreamUnavailable, request_json
from nivaro_orders.infrastructure.reservations import ServiceToken
from nivaro_orders.settings import Settings


class SourceError(CheckoutError):
    def __init__(self, code: str, status: int) -> None:
        self.status = status
        super().__init__(code)


class CustomerContext(Contract):
    customer_id: UUID
    cart_token: str | None
    address_token: str | None


class StaffContext(Contract):
    actor_id: UUID


type StaffArea = Literal["orders", "payments", "payment_reconciliation"]


class ErrorCode(BaseModel):
    code: str


class ErrorEnvelope(BaseModel):
    error: ErrorCode


def parse[T: BaseModel](contract: type[T], body: object) -> T:
    try:
        return contract.model_validate(body)
    except ValidationError as exc:
        raise UpstreamUnavailable() from exc


def authorization(access_token: str | None) -> dict[str, str]:
    if not access_token or len(access_token) > 8192:
        raise UpstreamUnavailable()
    return {"Authorization": f"Bearer {access_token}"}


class CheckoutSources:
    def __init__(self, http: httpx.AsyncClient, settings: Settings, secret: str) -> None:
        self.http = http
        self.identity = str(settings.identity_url).rstrip("/")
        self.cart = str(settings.cart_url).rstrip("/")
        self.catalog = str(settings.catalog_url).rstrip("/")
        self.auth = ("orders", secret)

    async def staff(
        self, access: str, mutation: dict[str, str] | None, *, area: StaffArea = "orders"
    ) -> StaffContext:
        payload: dict[str, object] = {"staff_access": access, "mutation": mutation}
        if area != "orders":
            payload["area"] = area
        status, body = await request_json(
            self.http,
            "POST",
            self.identity + "/internal/v1/orders/staff-context",
            auth=self.auth,
            json_body=payload,
        )
        if status in {401, 403}:
            code = parse(ErrorEnvelope, body).error.code
            if code != "service.unauthorized":
                raise SourceError(code, status)
        if status != 200:
            raise UpstreamUnavailable()
        return parse(StaffContext, body)

    async def customer(self, access: str, mutation: dict[str, str] | None) -> CustomerContext:
        status, body = await request_json(
            self.http,
            "POST",
            self.identity + "/internal/v1/orders/checkout-context",
            auth=self.auth,
            json_body={"customer_access": access, "mutation": mutation},
        )
        if status in {401, 403}:
            code = parse(ErrorEnvelope, body).error.code
            if code == "session.invalid":
                raise SourceError(code, 401)
            if code in {"csrf.invalid", "origin.forbidden"}:
                raise SourceError(code, 403)
        if status != 200:
            raise UpstreamUnavailable()
        return parse(CustomerContext, body)

    async def load_cart(self, context: CustomerContext, intent: CheckoutIntent) -> CartSnapshot:
        status, body = await request_json(
            self.http,
            "GET",
            self.cart + f"/internal/v1/orders/carts/{intent.market}",
            headers=authorization(context.cart_token),
            params={"version": str(intent.cart_version)},
            max_bytes=65536,
        )
        if status in {404, 409} and parse(ErrorEnvelope, body).error.code in {
            "cart.not_found",
            "cart.version_conflict",
        }:
            raise SourceError("checkout.cart_changed", 409)
        if status != 200:
            raise UpstreamUnavailable()
        cart = parse(CartSnapshot, body)
        if (cart.market, cart.currency, cart.version) != (
            intent.market,
            intent.currency,
            intent.cart_version,
        ):
            raise UpstreamUnavailable()
        if not cart.lines:
            raise SourceError("checkout.cart_empty", 409)
        return cart

    async def load_address(
        self, context: CustomerContext, intent: CheckoutIntent
    ) -> AddressSnapshot:
        status, body = await request_json(
            self.http,
            "GET",
            self.identity + f"/internal/v1/orders/addresses/{intent.address_id}",
            headers=authorization(context.address_token),
            params={"version": str(intent.address_version)},
        )
        if status in {404, 409} and parse(ErrorEnvelope, body).error.code in {
            "address.not_found",
            "address.changed",
        }:
            raise SourceError("checkout.address_changed", 409)
        if status != 200:
            raise UpstreamUnavailable()
        address = parse(AddressSnapshot, body)
        if (address.id, address.version) != (intent.address_id, intent.address_version):
            raise UpstreamUnavailable()
        return address

    async def snapshots(
        self, context: CustomerContext, intent: CheckoutIntent
    ) -> tuple[CartSnapshot, AddressSnapshot]:
        cart, address = await asyncio.gather(
            self.load_cart(context, intent), self.load_address(context, intent)
        )
        return cart, address

    async def quote(
        self, customer_id: UUID, operation_id: UUID, quote_id: UUID, cart: CartSnapshot
    ) -> CatalogQuote:
        status, body = await request_json(
            self.http,
            "POST",
            self.identity + "/internal/v1/service-tokens",
            auth=self.auth,
            json_body={"audience": "nivaro-catalog", "scope": "catalog.quote"},
        )
        if status != 200:
            raise UpstreamUnavailable()
        headers = authorization(parse(ServiceToken, body).access_token)
        status, body = await request_json(
            self.http,
            "POST",
            self.catalog + "/internal/v1/catalog/quotes",
            headers=headers,
            json_body={
                "quote_id": str(quote_id),
                "operation_id": str(operation_id),
                "customer_id": str(customer_id),
                "cart": cart.model_dump(mode="json"),
            },
            max_bytes=4 * 1024 * 1024,
        )
        if status == 409:
            code = parse(ErrorEnvelope, body).error.code
            if code in {
                "build.not_compatible",
                "build.invalid_selection",
                "inventory.insufficient_stock",
                "quote.eligibility_changed",
                "quote.conflicting_request",
            }:
                raise SourceError(code, 409)
        if status != 200:
            raise UpstreamUnavailable()
        quote = parse(CatalogQuote, body)
        if (quote.id, quote.operation_id, quote.customer_id, quote.cart_id) != (
            quote_id,
            operation_id,
            customer_id,
            cart.id,
        ):
            raise UpstreamUnavailable()
        return quote
