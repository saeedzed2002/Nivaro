import asyncio
import os
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import func, select, text, update

from nivaro_orders.application.checkout import begin_checkout, review_checkout, stage_order
from nivaro_orders.domain.checkout import (
    AddressSnapshot,
    CatalogQuote,
    CheckoutError,
    CheckoutIntent,
    DeliveryRate,
    Discount,
    QuotedGroup,
    QuotedLine,
    calculate_totals,
)
from nivaro_orders.infrastructure.database import Database
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
from nivaro_orders.settings import Settings


def address(country="IR"):
    return AddressSnapshot(
        id=uuid4(),
        version=1,
        label="Home",
        recipient="Test customer",
        country=country,
        city="Synthetic city",
        postal_code="1234567890",
        street="Synthetic test address",
        phone="+12025550100",
    )


def quote(operation_id, customer_id, *, market="ir", amount=1010, grouped=False):
    variant, now, group_id = uuid4(), datetime.now(UTC), uuid4() if grouped else None
    lines = [
        QuotedLine(
            id=uuid4(),
            version=2,
            variant_id=variant,
            quantity=1,
            group_id=group_id,
            slot_key="cpu" if grouped else None,
            product_id=uuid4(),
            product_name="Fixture",
            sku="TEST-CPU",
            specifications={"kind": "cpu"},
            spec_version=5,
            unit_price_minor=amount,
            price_version=3,
        )
    ]
    groups = []
    if group_id is not None:
        groups.append(
            QuotedGroup(
                id=group_id,
                version=4,
                name="Test build",
                mode="parts_only",
                requires_dedicated_gpu=False,
                source_build_id=uuid4(),
                source_build_version=7,
                selection_hash="c" * 64,
                spec_versions={str(variant): 5},
                ruleset_version="fixture",
                status="incomplete",
                findings=[],
                evaluated_at=now,
            )
        )
    return CatalogQuote(
        id=uuid4(),
        operation_id=operation_id,
        customer_id=customer_id,
        cart_id=uuid4(),
        cart_version=2,
        cart_fingerprint="a" * 64,
        lines=lines,
        groups=groups,
        subtotal_minor=amount,
        expires_at=now + timedelta(minutes=5),
        market=market,
        currency="IRR" if market == "ir" else "USD",
    )


def rate(country="IR"):
    if country == "IR":
        return DeliveryRate(
            market="ir",
            currency="IRR",
            country="IR",
            policy_version="synthetic-ir",
            shipping_minor=200,
            tax_basis_points=900,
            tax_included=False,
            shipping_taxable=False,
        )
    return DeliveryRate(
        market="international",
        currency="USD",
        country="US",
        policy_version="synthetic-us",
        shipping_minor=111,
        tax_basis_points=1000,
        tax_included=True,
        shipping_taxable=True,
    )


def test_market_money_coupons_and_tax_inclusion():
    ir = quote(uuid4(), uuid4())
    result = calculate_totals(ir, address(), rate(), Discount(kind="percentage", value=1500))
    assert (result.currency, result.discount_minor, result.tax_minor, result.total_minor) == (
        "IRR",
        150,
        70,
        1130,
    )
    usd = quote(uuid4(), uuid4(), market="international", amount=1001)
    result = calculate_totals(
        usd,
        address("US"),
        rate("US"),
        Discount(kind="percentage", value=5000, maximum_minor=125),
    )
    assert (result.currency, result.discount_minor, result.tax_minor, result.total_minor) == (
        "USD",
        125,
        89,
        987,
    )
    with pytest.raises(CheckoutError, match="checkout.delivery_unavailable"):
        calculate_totals(usd, address("US"), rate(), None)
    with pytest.raises(CheckoutError, match="coupon.minimum_spend"):
        calculate_totals(
            ir, address(), rate(), Discount(kind="fixed", value=150, minimum_minor=1200)
        )
    with pytest.raises(ValueError, match="whole tomans"):
        quote(uuid4(), uuid4(), amount=1011)


@pytest.fixture
async def database():
    settings = Settings(db_pool_size=20)
    if os.getenv("ORDERS_DISPOSABLE_TESTS") != "1":
        pytest.skip("Disposable Orders test database required")
    assert settings.db_host.startswith("nivaro-orders-qa-")
    db = Database(settings)
    yield db
    await db.engine.dispose()


class CheckoutFixture:
    def __init__(self, database):
        self.db = database
        self.address = address()
        self.intent = CheckoutIntent(
            market="ir",
            currency="IRR",
            cart_version=2,
            address_id=self.address.id,
            address_version=self.address.version,
        )
        self.rates = [rate()]

    async def request(self, customer, key, intent=None):
        async with self.db.sessions() as session:
            return await begin_checkout(session, customer, key, intent or self.intent)

    async def review(self, current_quote):
        async with self.db.sessions() as session:
            return await review_checkout(
                session,
                current_quote.customer_id,
                current_quote,
                self.address,
                self.rates,
            )

    async def save(self, current_quote, review):
        async with self.db.sessions() as session:
            return await stage_order(
                session,
                current_quote.customer_id,
                current_quote,
                self.address,
                self.rates,
                review.confirmation,
            )


async def test_checkout_idempotency_and_immutable_grouped_snapshot(database):
    checkout = CheckoutFixture(database)
    customer = uuid4()
    keys = await asyncio.gather(*(checkout.request(customer, "same-key") for _ in range(20)))
    assert len(set(keys)) == 1
    (operation,) = set(keys)
    assert await checkout.request(uuid4(), "same-key") != operation
    with pytest.raises(CheckoutError, match="checkout.idempotency_conflict"):
        await checkout.request(
            customer, "same-key", checkout.intent.model_copy(update={"cart_version": 3})
        )
    current_quote = quote(operation, customer, grouped=True)
    review = await checkout.review(current_quote)
    checkout.rates = [rate().model_copy(update={"shipping_minor": 300})]
    with pytest.raises(CheckoutError, match="checkout.confirmation_changed"):
        await checkout.save(current_quote, review)
    async with database.sessions() as db:
        assert await db.get(Order, operation) is None
    checkout.rates = [rate()]
    results = await asyncio.gather(*(checkout.save(current_quote, review) for _ in range(4)))
    assert {row.id for row in results} == {operation}
    assert {row.status for row in results} == {"pending_reservation"}
    checkout.address = checkout.address.model_copy(update={"street": "Changed source address"})
    assert (await checkout.save(current_quote, review)).id == operation
    async with database.sessions() as db:
        saved_address = await db.get(OrderAddress, operation)
        saved_group = await db.get(OrderConfiguration, (operation, current_quote.groups[0].id))
        saved_line = await db.get(OrderItem, (operation, current_quote.lines[0].id))
        assert saved_address.snapshot["street"] == "Synthetic test address"
        assert saved_group.snapshot["source_build_id"] == str(
            current_quote.groups[0].source_build_id
        )
        assert saved_line.unit_price_minor == 1010 and saved_line.spec_version == 5
        assert saved_line.source_group_id == current_quote.groups[0].id
        assert await db.get(OrderTransition, (operation, 1)) is not None
        assert (await db.get(CheckoutOperation, operation)).state == "pending_reservation"


@pytest.mark.parametrize(("limit", "single_customer"), [(1, False), (4, True)])
async def test_coupon_quota_is_atomic_and_expiry_frees_capacity(database, limit, single_customer):
    checkout = CheckoutFixture(database)
    coupon_id, now = uuid4(), datetime.now(UTC)
    code = "TEST-" + coupon_id.hex.upper()
    checkout.intent = checkout.intent.model_copy(update={"coupon_code": code})
    async with database.sessions() as db, db.begin():
        db.add(
            Coupon(
                id=coupon_id,
                code=code,
                market="ir",
                currency="IRR",
                kind="fixed",
                value=100,
                minimum_minor=0,
                maximum_minor=None,
                starts_at=now - timedelta(minutes=1),
                ends_at=now + timedelta(minutes=5),
                global_limit=limit,
                per_customer_limit=1,
                enabled=True,
            )
        )
    customer = uuid4()
    customers = [customer if single_customer else uuid4() for _ in range(20)]
    ids = await asyncio.gather(
        *(checkout.request(actor, str(index)) for index, actor in enumerate(customers))
    )
    quotes = [quote(operation, actor) for operation, actor in zip(ids, customers, strict=True)]
    reviews = await asyncio.gather(*(checkout.review(item) for item in quotes))
    results = await asyncio.gather(
        *(checkout.save(item, review) for item, review in zip(quotes, reviews, strict=True)),
        return_exceptions=True,
    )
    accepted = [result for result in results if isinstance(result, Order)]
    assert len(accepted) == 1
    errors = [result for result in results if isinstance(result, CheckoutError)]
    assert len(errors) == 19 and all(error.code == "coupon.quota_exhausted" for error in errors)
    async with database.sessions() as db, db.begin():
        assert (
            await db.scalar(
                select(func.count())
                .select_from(CouponClaim)
                .where(CouponClaim.coupon_id == coupon_id)
            )
            == 1
        )
        await db.execute(
            update(CouponClaim)
            .where(CouponClaim.order_id == accepted[0].id)
            .values(expires_at=now - timedelta(seconds=1))
        )
    retry = next(item for item in quotes if item.operation_id != accepted[0].id)
    assert (await checkout.save(retry, await checkout.review(retry))).discount_minor == 100


async def test_role_cannot_connect_to_catalog_database(database):
    async with database.sessions() as db:
        assert await db.scalar(text("SELECT current_database()")) == "nivaro_orders"
        assert not await db.scalar(
            text("SELECT has_database_privilege('nivaro_catalog', 'CONNECT')")
        )
        assert not await db.scalar(
            text(
                "SELECT rolsuper OR rolcreatedb OR rolcreaterole FROM pg_roles WHERE rolname = current_user"
            )
        )
