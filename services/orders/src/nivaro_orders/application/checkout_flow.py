from datetime import datetime
from typing import Literal
from uuid import UUID, uuid5

from sqlalchemy import select

from nivaro_orders.application.checkout import (
    begin_checkout,
    fingerprint,
    owned_operation,
    price_checkout,
    stage_order,
)
from nivaro_orders.application.reservations import Reservations, advance_reservation
from nivaro_orders.domain.checkout import (
    CartSnapshot,
    CatalogQuote,
    CheckoutError,
    CheckoutIntent,
    Contract,
    Digest,
    Totals,
)
from nivaro_orders.infrastructure.checkout_sources import CheckoutSources, CustomerContext
from nivaro_orders.infrastructure.database import Database
from nivaro_orders.infrastructure.http_json import UpstreamUnavailable
from nivaro_orders.infrastructure.models import CheckoutPreview, Order
from nivaro_orders.settings import Settings


class ReviewLine(Contract):
    id: UUID
    group_id: UUID | None
    name: str
    quantity: int
    unit_price_minor: int


class ReviewGroup(Contract):
    id: UUID
    name: str
    mode: Literal["complete_build", "parts_only"]
    status: Literal["compatible", "incompatible", "needs_review", "incomplete"]


class PreviewResponse(Contract):
    operation_id: UUID
    confirmation: Digest
    expires_at: datetime
    totals: Totals
    lines: list[ReviewLine]
    groups: list[ReviewGroup]


class ConfirmPreview(Contract):
    confirmation: Digest


class OrderStatus(Contract):
    id: UUID
    status: Literal[
        "pending_reservation",
        "awaiting_payment",
        "expired",
        "cancelled",
        "payment_processing",
        "payment_review",
        "paid",
    ]
    version: int
    totals: Totals
    reservation_expires_at: datetime | None
    failure_code: str | None


def fingerprint_cart(cart: CartSnapshot) -> str:
    # Catalog's wire contract sorts stable identifiers before canonical JSON hashing.
    content = cart.model_dump(mode="json")
    for field in ("lines", "groups"):
        content[field].sort(key=lambda item: item["id"])
    return fingerprint(content)


def preview_response(preview: CheckoutPreview) -> PreviewResponse:
    quote = CatalogQuote.model_validate(preview.quote_snapshot)
    return PreviewResponse(
        operation_id=preview.operation_id,
        confirmation=preview.confirmation,
        expires_at=quote.expires_at,
        totals=Totals.model_validate(preview.totals_snapshot),
        lines=[
            ReviewLine(
                id=line.id,
                group_id=line.group_id,
                name=line.product_name,
                quantity=line.quantity,
                unit_price_minor=line.unit_price_minor,
            )
            for line in quote.lines
        ],
        groups=[
            ReviewGroup(id=group.id, name=group.name, mode=group.mode, status=group.status)
            for group in quote.groups
        ],
    )


class CheckoutFlow:
    def __init__(
        self,
        database: Database,
        settings: Settings,
        sources: CheckoutSources,
        reservations: Reservations,
    ) -> None:
        self.database = database
        self.rates = settings.delivery_rates
        self.sources = sources
        self.reservations = reservations

    async def preview(
        self, customer: CustomerContext, key: str, intent: CheckoutIntent
    ) -> PreviewResponse:
        async with self.database.sessions() as db:
            operation_id = await begin_checkout(db, customer.customer_id, key, intent)
            existing = await db.get(CheckoutPreview, operation_id)
            if existing is not None:
                return preview_response(existing)

        cart, address = await self.sources.snapshots(customer, intent)
        quote = await self.sources.quote(
            customer.customer_id, operation_id, uuid5(operation_id, "catalog-checkout-quote"), cart
        )
        if quote.cart_fingerprint != fingerprint_cart(cart):
            raise UpstreamUnavailable()

        async with self.database.sessions.begin() as db:
            operation = await owned_operation(db, operation_id, customer.customer_id, lock=True)
            existing = await db.get(CheckoutPreview, operation_id)
            if existing is not None:
                return preview_response(existing)
            if operation.state != "started":
                raise CheckoutError("checkout.already_confirmed")
            priced = await price_checkout(
                db, operation, quote, address, self.rates, lock_coupon=False
            )
            review = CheckoutPreview(
                operation_id=operation_id,
                quote_snapshot=quote.model_dump(mode="json"),
                address_fingerprint=fingerprint(address.model_dump(mode="json")),
                totals_snapshot=priced.review.totals.model_dump(mode="json"),
                confirmation=priced.review.confirmation,
            )
            db.add(review)
            return preview_response(review)

    async def confirm(
        self, customer: CustomerContext, operation_id: UUID, confirmation: str
    ) -> OrderStatus:
        async with self.database.sessions() as db:
            operation = await owned_operation(db, operation_id, customer.customer_id, lock=False)
            review = await db.get(CheckoutPreview, operation_id)
            if review is None:
                raise CheckoutError("checkout.not_found")
            if review.confirmation != confirmation:
                raise CheckoutError("checkout.confirmation_changed")
            intent = CheckoutIntent.model_validate(operation.intent)
            quote = CatalogQuote.model_validate(review.quote_snapshot)
            address_fingerprint = review.address_fingerprint
            staged = await db.get(Order, operation_id) is not None

        if not staged:
            try:
                current_cart, current_address = await self.sources.snapshots(customer, intent)
                if fingerprint_cart(current_cart) != quote.cart_fingerprint:
                    raise CheckoutError("checkout.cart_changed")
                if fingerprint(current_address.model_dump(mode="json")) != address_fingerprint:
                    raise CheckoutError("checkout.address_changed")
                async with self.database.sessions() as db:
                    await stage_order(
                        db, customer.customer_id, quote, current_address, self.rates, confirmation
                    )
            except (CheckoutError, UpstreamUnavailable):
                # A concurrent confirmation can stage the same order while this
                # caller is checking snapshots. Its exact receipt remains replayable.
                async with self.database.sessions() as db:
                    if await db.get(Order, operation_id) is None:
                        raise

        await advance_reservation(self.database.sessions, self.reservations, operation_id)
        return await self.status(customer.customer_id, operation_id)

    async def status(self, customer_id: UUID, operation_id: UUID) -> OrderStatus:
        async with self.database.sessions() as db:
            order = await db.scalar(
                select(Order).where(Order.id == operation_id, Order.customer_id == customer_id)
            )
            if order is None:
                raise CheckoutError("checkout.not_found")
            return OrderStatus.model_validate(
                {
                    "id": order.id,
                    "status": order.status,
                    "version": order.version,
                    "totals": Totals.model_validate(order, from_attributes=True),
                    "reservation_expires_at": order.reservation_expires_at,
                    "failure_code": order.reservation_error,
                }
            )
