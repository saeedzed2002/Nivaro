import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from nivaro_orders.domain.checkout import (
    AddressSnapshot,
    CatalogQuote,
    CheckoutError,
    CheckoutIntent,
    DeliveryRate,
    Discount,
    Totals,
    calculate_totals,
)
from nivaro_orders.infrastructure.models import (
    CheckoutOperation,
    Coupon,
    CouponClaim,
    Order,
    OrderAddress,
    OrderConfiguration,
    OrderItem,
    OrderTransition,
)


def fingerprint(payload: dict[str, object]) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


async def begin_checkout(
    db: AsyncSession, customer_id: UUID, key: str, intent: CheckoutIntent
) -> UUID:
    if not re.fullmatch(r"[A-Za-z0-9._-]{1,128}", key):
        raise CheckoutError("checkout.invalid_idempotency_key")
    content = intent.model_dump(mode="json")
    digest = fingerprint(content)
    async with db.begin():
        operation_id: UUID | None = await db.scalar(
            insert(CheckoutOperation)
            .values(
                id=uuid4(),
                customer_id=customer_id,
                idempotency_key=key,
                fingerprint=digest,
                intent=content,
                state="started",
            )
            .on_conflict_do_nothing(constraint="uq_checkout_customer_key")
            .returning(CheckoutOperation.id)
        )
        if operation_id is not None:
            return operation_id
        existing = (
            await db.scalars(
                select(CheckoutOperation).where(
                    CheckoutOperation.customer_id == customer_id,
                    CheckoutOperation.idempotency_key == key,
                )
            )
        ).one()
        if existing.fingerprint != digest:
            raise CheckoutError("checkout.idempotency_conflict")
        return existing.id


async def owned_operation(
    db: AsyncSession, operation_id: UUID, customer_id: UUID, *, lock: bool
) -> CheckoutOperation:
    statement = select(CheckoutOperation).where(
        CheckoutOperation.id == operation_id, CheckoutOperation.customer_id == customer_id
    )
    if lock:
        statement = statement.with_for_update()
    operation = await db.scalar(statement)
    if operation is None:
        raise CheckoutError("checkout.not_found")
    return operation


@dataclass(frozen=True)
class Review:
    totals: Totals
    confirmation: str


@dataclass(frozen=True)
class PricedCheckout:
    review: Review
    rate: DeliveryRate
    coupon: Coupon | None
    discount: Discount | None


async def find_coupon(db: AsyncSession, intent: CheckoutIntent, *, lock: bool) -> Coupon | None:
    if intent.coupon_code is None:
        return None
    statement = select(Coupon).where(
        Coupon.code == intent.coupon_code, Coupon.market == intent.market
    )
    if lock:
        statement = statement.with_for_update()
    coupon = await db.scalar(statement)
    if coupon is None or coupon.currency != intent.currency or not coupon.enabled:
        raise CheckoutError("coupon.unavailable")
    return coupon


async def require_coupon_capacity(
    db: AsyncSession, coupon: Coupon, customer_id: UUID, now: datetime
) -> None:
    if not coupon.starts_at <= now < coupon.ends_at:
        raise CheckoutError("coupon.unavailable")
    overall, customer = (
        await db.execute(
            select(
                func.count(),
                func.count().filter(CouponClaim.customer_id == customer_id),
            )
            .select_from(CouponClaim)
            .where(
                CouponClaim.coupon_id == coupon.id,
                CouponClaim.state.in_(("finalizing", "consumed"))
                | ((CouponClaim.state == "held") & (CouponClaim.expires_at > now)),
            )
        )
    ).one()
    if overall >= coupon.global_limit or customer >= coupon.per_customer_limit:
        raise CheckoutError("coupon.quota_exhausted")


async def price_checkout(
    db: AsyncSession,
    operation: CheckoutOperation,
    quote: CatalogQuote,
    address: AddressSnapshot,
    rates: list[DeliveryRate],
    *,
    lock_coupon: bool,
) -> PricedCheckout:
    intent = CheckoutIntent.model_validate(operation.intent)
    if (
        quote.operation_id,
        quote.customer_id,
        quote.market,
        quote.currency,
        quote.cart_version,
    ) != (operation.id, operation.customer_id, intent.market, intent.currency, intent.cart_version):
        raise CheckoutError("checkout.quote_mismatch")
    if (address.id, address.version) != (intent.address_id, intent.address_version):
        raise CheckoutError("checkout.address_changed")
    rate = next(
        (r for r in rates if (r.market, r.country) == (intent.market, address.country)), None
    )
    if rate is None:
        raise CheckoutError("checkout.delivery_unavailable")
    coupon = await find_coupon(db, intent, lock=lock_coupon)
    now: datetime = (await db.execute(select(func.clock_timestamp()))).scalar_one()
    if quote.expires_at <= now:
        raise CheckoutError("checkout.quote_expired")
    discount = None
    if coupon is not None:
        await require_coupon_capacity(db, coupon, operation.customer_id, now)
        discount = Discount.model_validate(
            {
                "kind": coupon.kind,
                "value": coupon.value,
                "minimum_minor": coupon.minimum_minor,
                "maximum_minor": coupon.maximum_minor,
            }
        )
    totals = calculate_totals(quote, address, rate, discount)
    confirmation = fingerprint(
        {
            "operation": str(operation.id),
            "quote": str(quote.id),
            "cart_fingerprint": quote.cart_fingerprint,
            "address": [str(address.id), address.version],
            "totals": totals.model_dump(mode="json"),
            # Unset thresholds preserve confirmations issued before the policy field existed.
            "delivery": rate.model_dump(mode="json", exclude_none=True),
            "coupon": str(coupon.id) if coupon else None,
        }
    )
    return PricedCheckout(Review(totals, confirmation), rate, coupon, discount)


async def review_checkout(
    db: AsyncSession,
    customer_id: UUID,
    quote: CatalogQuote,
    address: AddressSnapshot,
    rates: list[DeliveryRate],
) -> Review:
    async with db.begin():
        operation = await owned_operation(db, quote.operation_id, customer_id, lock=False)
        if operation.state != "started":
            raise CheckoutError("checkout.already_confirmed")
        return (
            await price_checkout(db, operation, quote, address, rates, lock_coupon=False)
        ).review


async def stage_order(
    db: AsyncSession,
    customer_id: UUID,
    quote: CatalogQuote,
    address: AddressSnapshot,
    rates: list[DeliveryRate],
    confirmation: str,
) -> Order:
    async with db.begin():
        operation = await owned_operation(db, quote.operation_id, customer_id, lock=True)
        existing = await db.get(Order, operation.id)
        if existing is not None:
            if (existing.quote_id, existing.confirmation) != (quote.id, confirmation):
                raise CheckoutError("checkout.already_confirmed")
            return existing

        # Hold the coupon row from the quota read through claim insertion. Every
        # quota-changing workflow must take that lock before inspecting claims.
        priced = await price_checkout(db, operation, quote, address, rates, lock_coupon=True)
        if priced.review.confirmation != confirmation:
            raise CheckoutError("checkout.confirmation_changed")
        order = Order(
            id=operation.id,
            customer_id=customer_id,
            status="pending_reservation",
            version=1,
            cart_id=quote.cart_id,
            cart_version=quote.cart_version,
            cart_fingerprint=quote.cart_fingerprint,
            quote_id=quote.id,
            quote_expires_at=quote.expires_at,
            confirmation=confirmation,
            delivery_policy=priced.rate.model_dump(mode="json", exclude_none=True),
            **priced.review.totals.model_dump(),
        )
        operation.state = "pending_reservation"
        db.add(order)
        await db.flush()
        db.add(OrderAddress(order_id=order.id, snapshot=address.model_dump(mode="json")))
        db.add_all(
            OrderConfiguration(
                order_id=order.id, source_group_id=group.id, snapshot=group.model_dump(mode="json")
            )
            for group in quote.groups
        )
        await db.flush()
        db.add_all(
            OrderItem(
                order_id=order.id,
                source_line_id=line.id,
                source_line_version=line.version,
                source_group_id=line.group_id,
                slot_key=line.slot_key,
                product_id=line.product_id,
                variant_id=line.variant_id,
                sku=line.sku,
                name=line.product_name,
                quantity=line.quantity,
                unit_price_minor=line.unit_price_minor,
                spec_version=line.spec_version,
                specifications=line.specifications,
                price_version=line.price_version,
            )
            for line in quote.lines
        )
        db.add(
            OrderTransition(
                order_id=order.id,
                version=order.version,
                customer_id=customer_id,
                status=order.status,
                reason="checkout.confirmed",
            )
        )
        if priced.coupon is not None and priced.discount is not None:
            db.add(
                CouponClaim(
                    order_id=order.id,
                    coupon_id=priced.coupon.id,
                    customer_id=customer_id,
                    state="held",
                    amount_minor=order.discount_minor,
                    # The orchestrator will replace this provisional deadline with
                    # the actual inventory deadline after acknowledging the hold.
                    expires_at=quote.expires_at + timedelta(minutes=15),
                    snapshot={
                        "code": priced.coupon.code,
                        **priced.discount.model_dump(mode="json"),
                    },
                )
            )
        return order
