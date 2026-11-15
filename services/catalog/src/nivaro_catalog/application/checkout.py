from collections import Counter
from datetime import datetime, timedelta
from typing import Literal
from uuid import UUID

from sqlalchemy import Select, func, insert, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from nivaro_catalog.domain import evaluation
from nivaro_catalog.domain.checkout import (
    CartSnapshot,
    CheckoutError,
    Quote,
    QuotedGroup,
    QuotedLine,
    QuoteRequest,
    Reservation,
    ReservationRequest,
)
from nivaro_catalog.domain.contracts import Market, Offer, Variant
from nivaro_catalog.infrastructure.models import (
    AllocationRow,
    ProductRow,
    QuoteRow,
    ReservationRow,
    VariantRow,
)
from nivaro_catalog.infrastructure.repository import variant_contract

QUOTE_LIFETIME = timedelta(minutes=5)
HOLD_LIFETIME = timedelta(minutes=15)
Action = Literal["read", "commit", "release"]


async def database_time(db: AsyncSession) -> datetime:
    now: datetime = (await db.execute(select(func.clock_timestamp()))).scalar_one()
    return now


async def lock_identifier(db: AsyncSession, namespace: str, identifier: UUID) -> None:
    # Serializes creation even before the row exists. A hash collision only delays the caller.
    await db.execute(
        select(func.pg_advisory_xact_lock(func.hashtextextended(f"{namespace}:{identifier}", 0)))
    )


def ordered_variants(ids: set[UUID]) -> Select[VariantRow]:
    return select(VariantRow).where(VariantRow.id.in_(ids)).order_by(VariantRow.id)


async def sale_rows(
    db: AsyncSession, ids: set[UUID]
) -> tuple[dict[UUID, ProductRow], dict[UUID, VariantRow]]:
    # Administration locks product -> variant -> offer. Hold the product against
    # publication changes and the variant against offer/spec/stock changes until commit.
    products = {
        row.id: row
        for row in await db.scalars(
            select(ProductRow)
            .where(ProductRow.id.in_(select(VariantRow.product_id).where(VariantRow.id.in_(ids))))
            .order_by(ProductRow.id)
            .with_for_update(read=True)
        )
    }
    variants = {
        row.id: row
        for row in await db.scalars(
            ordered_variants(ids).options(selectinload(VariantRow.offers)).with_for_update()
        )
    }
    if ids != variants.keys():
        raise CheckoutError("quote.eligibility_changed", "A selected SKU no longer exists")
    return products, variants


def sellable_offer(product: ProductRow, variant: Variant, market: Market) -> Offer:
    if product.status != "published" or not product.image_ready:
        raise CheckoutError("quote.eligibility_changed", "The product is unavailable")
    offer = next((item for item in variant.offers if item.market == market), None)
    if offer is None or offer.reference_only or not offer.available_for_sale:
        raise CheckoutError("quote.eligibility_changed", "The SKU has no sellable market offer")
    return offer


def check_stock(rows: dict[UUID, VariantRow], quantities: Counter[UUID]) -> None:
    for variant_id, quantity in quantities.items():
        variant = rows[variant_id]
        if not variant.stock_verified or variant.on_hand - variant.reserved < quantity:
            raise CheckoutError(
                "inventory.insufficient_stock",
                "Available stock is insufficient",
                409,
                str(variant_id),
            )


def evaluate_groups(
    cart: CartSnapshot, variants: dict[UUID, Variant], now: datetime
) -> list[QuotedGroup]:
    groups = []
    for group in cart.groups:
        try:
            report = evaluation.evaluate(
                cart.evaluation_request(group),
                variants,
                ruleset_version=evaluation.RULESET_VERSION,
                evaluated_at=now,
            )
        except evaluation.SelectionError as exc:
            raise CheckoutError("build.invalid_selection", str(exc)) from exc
        if group.mode == "complete_build" and report.status != "compatible":
            raise CheckoutError(
                "build.not_compatible",
                "A complete build requires a compatible core configuration",
                409,
                str(group.id),
                report.status,
            )
        groups.append(
            QuotedGroup(
                **group.model_dump(),
                selection_hash=report.selection_hash,
                ruleset_version=report.ruleset_version,
                spec_versions=report.spec_versions,
                status=report.status,
                findings=report.findings,
                evaluated_at=report.evaluated_at,
            )
        )
    return groups


async def create_quote(db: AsyncSession, command: QuoteRequest) -> Quote:
    cart = command.cart
    fingerprint = cart.fingerprint()
    async with db.begin():
        await lock_identifier(db, "catalog-quote", command.quote_id)
        stored = await db.get(QuoteRow, command.quote_id)
        if stored is not None:
            quote = Quote.model_validate(stored.snapshot)
            if (quote.customer_id, quote.operation_id, quote.cart_fingerprint) != (
                command.customer_id,
                command.operation_id,
                fingerprint,
            ):
                raise CheckoutError("quote.conflicting_request", "Quote identifier is already used")
            return quote

        quantities: Counter[UUID] = Counter()
        for line in cart.lines:
            quantities[line.variant_id] += line.quantity
        products, rows = await sale_rows(db, set(quantities))
        variants = {variant_id: variant_contract(row) for variant_id, row in rows.items()}
        now = await database_time(db)
        lines = []
        for line in cart.lines:
            variant = variants[line.variant_id]
            product = products[rows[line.variant_id].product_id]
            offer = sellable_offer(product, variant, cart.market)
            lines.append(
                QuotedLine(
                    **line.model_dump(),
                    product_id=product.id,
                    product_name=product.name,
                    sku=variant.sku,
                    specifications=variant.specifications,
                    spec_version=variant.spec_version,
                    unit_price_minor=offer.amount_minor,
                    price_version=offer.price_version,
                )
            )
        groups = evaluate_groups(cart, variants, now)
        check_stock(rows, quantities)
        quote = Quote(
            id=command.quote_id,
            operation_id=command.operation_id,
            customer_id=command.customer_id,
            cart_id=cart.id,
            cart_version=cart.version,
            cart_fingerprint=fingerprint,
            market=cart.market,
            currency=cart.currency,
            lines=lines,
            groups=groups,
            subtotal_minor=sum(line.unit_price_minor * line.quantity for line in lines),
            expires_at=now + QUOTE_LIFETIME,
        )
        db.add(QuoteRow(id=quote.id, snapshot=quote.model_dump(mode="json")))
        return quote


async def load_quote(db: AsyncSession, quote_id: UUID) -> Quote:
    row = await db.get(QuoteRow, quote_id)
    if row is None:
        raise CheckoutError("quote.not_found", "Quote not found", 404)
    return Quote.model_validate(row.snapshot)


def receipt(row: ReservationRow, quote: Quote) -> Reservation:
    return Reservation.model_validate(
        {
            "operation_id": row.operation_id,
            "quote_id": row.quote_id,
            "customer_id": quote.customer_id,
            "state": row.state,
            "expires_at": row.expires_at,
            "market": quote.market,
            "currency": quote.currency,
        }
    )


async def reserve(db: AsyncSession, command: ReservationRequest) -> Reservation:
    operation_id = command.operation_id
    async with db.begin():
        await lock_identifier(db, "catalog-reservation", operation_id)
        quote = await load_quote(db, command.quote_id)
        if quote.customer_id != command.customer_id or quote.operation_id != operation_id:
            raise CheckoutError("quote.not_found", "Quote not found", 404)
        if quote.cart_fingerprint != command.cart_fingerprint:
            raise CheckoutError("build.selection_changed", "Cart snapshot differs from the quote")
        prior = await db.get(ReservationRow, operation_id, with_for_update=True)
        if prior is not None:
            if prior.quote_id != quote.id:
                raise CheckoutError("reservation.conflicting_request", "Operation already reserved")
            await change_state(db, prior, "read")
            return receipt(prior, quote)

        quantities: Counter[UUID] = Counter()
        for line in quote.lines:
            quantities[line.variant_id] += line.quantity
        products, rows = await sale_rows(db, set(quantities))
        now = await database_time(db)
        if quote.expires_at <= now:
            raise CheckoutError("quote.expired", "Confirm a new quote before reserving")
        if any(group.ruleset_version != evaluation.RULESET_VERSION for group in quote.groups):
            raise CheckoutError("build.validation_stale", "Compatibility rules changed")
        variants = {variant_id: variant_contract(row) for variant_id, row in rows.items()}
        for line in quote.lines:
            variant = variants[line.variant_id]
            if variant.spec_version != line.spec_version:
                raise CheckoutError("build.validation_stale", "SKU specifications changed")
            offer = sellable_offer(
                products[rows[line.variant_id].product_id], variant, quote.market
            )
            if (offer.price_version, offer.amount_minor) != (
                line.price_version,
                line.unit_price_minor,
            ):
                raise CheckoutError("quote.price_changed", "Confirm the new offer before reserving")
        check_stock(rows, quantities)

        hold = ReservationRow(
            operation_id=operation_id,
            quote_id=quote.id,
            state="held",
            expires_at=now + HOLD_LIFETIME,
        )
        db.add(hold)
        await db.flush()
        await db.execute(
            insert(AllocationRow),
            [
                {"operation_id": operation_id, "variant_id": variant_id, "quantity": quantity}
                for variant_id, quantity in sorted(quantities.items())
            ],
        )
        for variant_id, quantity in quantities.items():
            rows[variant_id].reserved += quantity
            rows[variant_id].version += 1
        return receipt(hold, quote)


async def change_state(db: AsyncSession, row: ReservationRow, action: Action) -> None:
    if row.state != "held":
        if (row.state, action) in {("committed", "release"), ("released", "commit")}:
            raise CheckoutError("reservation.state_conflict", "Reservation is already finalized")
        return
    if action == "read" and row.expires_at > await database_time(db):
        return

    quantities = {
        allocation.variant_id: allocation.quantity
        for allocation in await db.scalars(
            select(AllocationRow).where(AllocationRow.operation_id == row.operation_id)
        )
    }
    variants = await db.scalars(ordered_variants(set(quantities)).with_for_update())
    # The DB clock is read after lock waits so a late commit cannot win by starting early.
    if row.expires_at <= await database_time(db):
        row.state = "expired"
    elif action == "read":
        return
    else:
        row.state = "committed" if action == "commit" else "released"
    for variant in variants:
        quantity = quantities[variant.id]
        variant.reserved -= quantity
        if row.state == "committed":
            variant.on_hand -= quantity
        variant.version += 1


async def reservation_action(
    db: AsyncSession, operation_id: UUID, customer_id: UUID, action: Action
) -> Reservation:
    async with db.begin():
        row = await db.get(ReservationRow, operation_id, with_for_update=True)
        if row is None:
            raise CheckoutError("reservation.not_found", "Reservation not found", 404)
        quote = await load_quote(db, row.quote_id)
        if quote.customer_id != customer_id:
            raise CheckoutError("reservation.not_found", "Reservation not found", 404)
        await change_state(db, row, action)
        return receipt(row, quote)


async def expire_one(db: AsyncSession) -> bool:
    async with db.begin():
        row = await db.scalar(
            select(ReservationRow)
            .where(
                ReservationRow.state == "held",
                ReservationRow.expires_at <= func.statement_timestamp(),
            )
            .order_by(ReservationRow.expires_at, ReservationRow.operation_id)
            .limit(1)
            .with_for_update(skip_locked=True)
        )
        if row is None:
            return False
        await change_state(db, row, "read")
        return True
