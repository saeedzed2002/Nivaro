import asyncio
import os
import sys
from contextlib import suppress
from datetime import UTC, datetime, timedelta
from json import dumps
from pathlib import Path
from uuid import uuid4

import aio_pika
import httpx
import psycopg
import pytest
from aio_pika.exceptions import DeliveryError
from sqlalchemy import func, select, text, update

from nivaro_orders.application.checkout import begin_checkout, review_checkout, stage_order
from nivaro_orders.application.reservations import advance_reservation, expire_unpaid
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
from nivaro_orders.domain.events import ExpiredReservation, ExpiryPayload
from nivaro_orders.expiry_consumer import apply_expiry
from nivaro_orders.infrastructure.database import Database
from nivaro_orders.infrastructure.models import (
    CheckoutOperation,
    Coupon,
    CouponClaim,
    InboxEvent,
    Order,
    OrderAddress,
    OrderConfiguration,
    OrderItem,
    OrderTransition,
)
from nivaro_orders.infrastructure.reservations import (
    CatalogReservations,
    Receipt,
    ReservationRejected,
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


async def test_definitive_stock_rejection_releases_the_coupon_claim(database):
    checkout = CheckoutFixture(database)
    customer = uuid4()
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
                global_limit=1,
                per_customer_limit=1,
                enabled=True,
            )
        )
    operation = await checkout.request(customer, "stock-rejected")
    current = quote(operation, customer)
    await checkout.save(current, await checkout.review(current))

    class UnavailableStock:
        async def recover_or_reserve(self, *_):
            raise ReservationRejected("inventory.insufficient_stock")

    assert await advance_reservation(database.sessions, UnavailableStock(), operation)
    assert not await advance_reservation(database.sessions, UnavailableStock(), operation)
    async with database.sessions() as db:
        order = await db.get(Order, operation)
        assert (order.status, order.reservation_error) == (
            "cancelled",
            "inventory.insufficient_stock",
        )
        assert (await db.get(CouponClaim, operation)).state == "released"
        assert (await db.get(CheckoutOperation, operation)).state == "reservation_failed"
        assert (
            await db.get(OrderTransition, (operation, 2))
        ).reason == "inventory.insufficient_stock"


class LoseSuccessfulReserveResponse(httpx.AsyncBaseTransport):
    def __init__(self):
        self.inner = httpx.AsyncHTTPTransport()
        self.writes = 0

    async def handle_async_request(self, request):
        response = await self.inner.handle_async_request(request)
        if request.method == "POST" and request.url.path == "/internal/v1/catalog/reservations":
            self.writes += 1
            if self.writes == 1 and response.status_code == 200:
                await response.aclose()
                raise httpx.ReadTimeout(
                    "Synthetic loss after Catalog committed the hold", request=request
                )
        return response

    async def aclose(self):
        await self.inner.aclose()


@pytest.mark.skipif(
    os.getenv("ORDERS_CATALOG_E2E") != "1", reason="Disposable catalog stack required"
)
async def test_lost_response_after_real_catalog_hold_is_recovered_by_operation_id(database):
    settings = Settings()
    secret = settings.client_secret_file.read_text().strip()
    checkout = CheckoutFixture(database)
    checkout.address = address("US")
    checkout.intent = CheckoutIntent(
        market="international",
        currency="USD",
        cart_version=2,
        address_id=checkout.address.id,
        address_version=checkout.address.version,
    )
    checkout.rates = [rate("US")]
    customer = uuid4()
    operation = await checkout.request(customer, "catalog-lost-response")
    transport = LoseSuccessfulReserveResponse()
    async with httpx.AsyncClient(transport=transport, timeout=5, trust_env=False) as http:
        catalog = str(settings.catalog_url).rstrip("/")
        identity = str(settings.identity_url).rstrip("/")
        product = await http.get(catalog + "/api/v1/catalog/products/amd-ryzen-7-9800x3d")
        product.raise_for_status()
        variant = product.json()["variants"][0]["id"]
        token_response = await http.post(
            identity + "/internal/v1/service-tokens",
            auth=("orders", secret),
            json={"audience": "nivaro-catalog", "scope": "catalog.quote"},
        )
        token_response.raise_for_status()

        async def stage_for(operation_id):
            quoted = await http.post(
                catalog + "/internal/v1/catalog/quotes",
                headers={"Authorization": "Bearer " + token_response.json()["access_token"]},
                json={
                    "quote_id": str(uuid4()),
                    "operation_id": str(operation_id),
                    "customer_id": str(customer),
                    "cart": {
                        "id": str(uuid4()),
                        "version": 2,
                        "market": "international",
                        "currency": "USD",
                        "lines": [
                            {"id": str(uuid4()), "variant_id": variant, "version": 1, "quantity": 1}
                        ],
                        "groups": [],
                    },
                },
            )
            assert quoted.is_success, quoted.text
            current = CatalogQuote.model_validate(quoted.json())
            await checkout.save(current, await checkout.review(current))
            return current

        await stage_for(operation)
        client = CatalogReservations(http, settings, secret)
        assert await advance_reservation(database.sessions, client, operation)
        async with database.sessions() as db, db.begin():
            saved = await db.get(Order, operation)
            assert (saved.status, saved.reservation_error) == (
                "pending_reservation",
                "reservation.unavailable",
            )
            await db.execute(
                update(Order).where(Order.id == operation).values(reservation_retry_at=None)
            )
        replies = await asyncio.gather(
            *(advance_reservation(database.sessions, client, operation) for _ in range(4))
        )
        assert replies.count(True) == 1
        assert transport.writes == 1
        async with database.sessions() as db:
            saved = await db.get(Order, operation)
            assert (saved.status, saved.reservation_attempts, saved.version) == (
                "awaiting_payment",
                2,
                2,
            )
            assert saved.reservation_expires_at is not None
            assert (await db.get(CheckoutOperation, operation)).state == "reservation_confirmed"
        summaries = await http.post(
            catalog + "/api/v1/catalog/variant-summaries",
            json={"market": "international", "currency": "USD", "variant_ids": [variant]},
        )
        summaries.raise_for_status()
        assert summaries.json()["items"][0]["available_quantity"] == 11

        background_order = await checkout.request(customer, "background-reservation")
        await stage_for(background_order)
        worker = await asyncio.create_subprocess_exec(
            sys.executable, "-m", "nivaro_orders.reservation_worker"
        )
        try:
            async with asyncio.timeout(20):
                while worker.returncode is None:
                    async with database.sessions() as db:
                        saved = await db.get(Order, background_order)
                        if saved.status == "awaiting_payment":
                            assert saved.reservation_attempts == 1
                            break
                    await asyncio.sleep(0.2)
                else:
                    pytest.fail("Reservation worker exited before processing the order")
        finally:
            with suppress(ProcessLookupError):
                worker.terminate()
            await worker.wait()

        if os.getenv("ORDERS_EVENT_E2E") == "1":
            event_operation = await checkout.request(customer, "durable-expiry")
            event_quote = await stage_for(event_operation)
            held = await client.recover_or_reserve(
                event_operation, event_quote.id, customer, event_quote.cart_fingerprint
            )
            assert held.state == "held"
            await verify_broker_expiry(database, client, event_quote)


async def verify_broker_expiry(database, client, current):
    settings = Settings()
    catalog_password = Path("/run/secrets/catalog_db_password").read_text().strip()
    async with await psycopg.AsyncConnection.connect(
        host=settings.db_host,
        dbname="nivaro_catalog",
        user="nivaro_catalog",
        password=catalog_password,
    ) as catalog_db:
        async with catalog_db.transaction():
            await catalog_db.execute(
                "UPDATE stock_reservations SET expires_at=clock_timestamp()-interval '1 second' WHERE operation_id=%s",
                (current.operation_id,),
            )
        result = await client.recover_or_reserve(
            current.operation_id, current.id, current.customer_id, current.cart_fingerprint
        )
        assert result.state == "expired"
        async with asyncio.timeout(15):
            while True:
                async with catalog_db.transaction():
                    rows = await catalog_db.execute(
                        "SELECT id,envelope,published_at FROM event_outbox WHERE aggregate_id=%s",
                        (current.operation_id,),
                    )
                    found = await rows.fetchall()
                async with database.sessions() as db:
                    saved = await db.get(Order, current.operation_id)
                    if found and found[0][2] is not None and saved.status == "expired":
                        event_id, envelope, _ = found[0]
                        assert len(found) == 1 and saved.version == 2
                        assert (
                            await db.scalar(
                                select(func.count())
                                .select_from(InboxEvent)
                                .where(InboxEvent.event_id == event_id)
                            )
                            == 1
                        )
                        break
                await asyncio.sleep(0.2)

    secret = Path("/run/secrets/catalog_event_broker_password").read_text().strip()
    async with await aio_pika.connect(
        host="rabbitmq",
        login="nivaro_catalog_events",
        password=secret,
        virtualhost="commerce-events",
        timeout=5,
    ) as broker:
        async with broker.channel(publisher_confirms=True, on_return_raises=True) as channel:
            exchange = await channel.get_exchange("nivaro.events", ensure=False)
            await exchange.publish(
                aio_pika.Message(
                    dumps(envelope).encode(),
                    content_type="application/json",
                    message_id=str(event_id),
                ),
                "inventory.reservation.expired",
                mandatory=True,
            )
            await exchange.publish(
                aio_pika.Message(b"{}", content_type="application/json", message_id=str(uuid4())),
                "inventory.reservation.expired",
                mandatory=True,
            )
            with pytest.raises(DeliveryError):
                await exchange.publish(
                    aio_pika.Message(b"{}"), "inventory.no-binding", mandatory=True
                )


async def test_replayed_expiry_records_one_inbox_effect(database):
    checkout = CheckoutFixture(database)
    customer = uuid4()
    operation = await checkout.request(customer, "event-replay")
    current = quote(operation, customer)
    await checkout.save(current, await checkout.review(current))
    now = datetime.now(UTC)
    event = ExpiredReservation(
        event_id=uuid4(),
        event_type="inventory.reservation.expired",
        schema_version=1,
        occurred_at=now,
        producer="catalog",
        aggregate_id=operation,
        aggregate_version=2,
        correlation_id=operation,
        causation_id=None,
        payload=ExpiryPayload(
            market="ir", currency="IRR", quote_id=current.id, expires_at=now - timedelta(seconds=1)
        ),
    )

    async def consume():
        async with database.sessions() as db:
            await apply_expiry(db, event)

    await asyncio.gather(*(consume() for _ in range(4)))
    async with database.sessions() as db:
        order = await db.get(Order, operation)
        assert (order.status, order.version) == ("expired", 2)
        assert (
            await db.scalar(
                select(func.count())
                .select_from(InboxEvent)
                .where(InboxEvent.event_id == event.event_id)
            )
            == 1
        )


async def test_expiry_updates_order_transition_once(database):
    checkout = CheckoutFixture(database)
    customer = uuid4()
    operation = await checkout.request(customer, "expires")
    current = quote(operation, customer)
    await checkout.save(current, await checkout.review(current))

    class ExistingHold:
        async def recover_or_reserve(self, operation_id, quote_id, customer_id, _):
            return Receipt(
                market="ir",
                currency="IRR",
                operation_id=operation_id,
                quote_id=quote_id,
                customer_id=customer_id,
                state="held",
                expires_at=datetime.now(UTC) + timedelta(minutes=10),
            )

    assert await advance_reservation(database.sessions, ExistingHold(), operation)
    async with database.sessions() as db, db.begin():
        await db.execute(
            update(Order)
            .where(Order.id == operation)
            .values(reservation_expires_at=func.clock_timestamp() - timedelta(seconds=1))
        )
    async with database.sessions() as db:
        assert await expire_unpaid(db)
        assert not await expire_unpaid(db)
        order = await db.get(Order, operation)
        assert (order.status, order.version) == ("expired", 3)
