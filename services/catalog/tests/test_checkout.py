"""Checkout concurrency and deadlines against real, disposable PostgreSQL."""

import asyncio
import os
from datetime import timedelta
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import delete, func, select, update

from nivaro_catalog.application.checkout import expire_one
from nivaro_catalog.domain.checkout import CartGroup, CartLine, CartSnapshot, QuoteRequest
from nivaro_catalog.domain.contracts import CPU, Prebuilt
from nivaro_catalog.domain.evaluation import selection_hash
from nivaro_catalog.infrastructure.database import Database
from nivaro_catalog.infrastructure.models import (
    AllocationRow,
    CategoryRow,
    OfferRow,
    ProductRow,
    QuoteRow,
    ReservationRow,
    VariantRow,
)
from nivaro_catalog.main import app
from nivaro_catalog.settings import Settings

pytestmark = pytest.mark.skipif(
    not os.getenv("CATALOG_DB_HOST") or os.getenv("CATALOG_DISPOSABLE_TESTS") != "1",
    reason="Dedicated disposable catalog database required",
)
ROOT = "/internal/v1/catalog"
EVIDENCE = {"url": "https://example.test/spec", "checked_on": "2026-10-27", "note": "Test only"}


class Fixture:
    def __init__(self, database, client):
        self.database, self.client = database, client
        self.products = []
        self.quotes = set()

    async def add(self, stock, spec=None, *, variant_id=None, reference=False):
        product_id, variant_id = uuid4(), variant_id or uuid4()
        self.products.append(product_id)
        spec = spec or CPU(model="TEST-CPU")
        async with self.database.sessions() as db, db.begin():
            category = await db.scalar(select(CategoryRow.id).limit(1))
            db.add(
                ProductRow(
                    id=product_id,
                    slug=f"checkout-{product_id}",
                    name="Checkout fixture",
                    description={"fa": "نمونه", "en": "Fixture"},
                    category_id=category,
                    brand="Test",
                    status="published",
                    image="test.png",
                    image_ready=True,
                    highlights=[],
                    search_tokens=[],
                )
            )
            await db.flush()
            db.add(
                VariantRow(
                    id=variant_id,
                    product_id=product_id,
                    sku=f"SKU-{variant_id}",
                    packaging={"fa": "نمونه", "en": "Fixture"},
                    specifications=spec.model_dump(mode="json"),
                    evidence=[EVIDENCE],
                    stock_kind="stocked_prebuilt" if isinstance(spec, Prebuilt) else "component",
                    on_hand=stock,
                    stock_verified=True,
                )
            )
            await db.flush()
            for market, currency, amount in (("ir", "IRR", 1000), ("international", "USD", 337)):
                db.add(
                    OfferRow(
                        id=uuid4(),
                        variant_id=variant_id,
                        market=market,
                        currency=currency,
                        amount_minor=amount,
                        available_for_sale=not reference,
                        reference_only=reference,
                        source=EVIDENCE,
                        seller="Fixture",
                    )
                )
        return variant_id

    def command(self, lines, groups=(), *, market="ir"):
        cart = CartSnapshot(
            id=uuid4(),
            version=1,
            market=market,
            currency="IRR" if market == "ir" else "USD",
            lines=[
                CartLine(id=uuid4(), version=1, variant_id=item, quantity=1)
                if not isinstance(item, CartLine)
                else item
                for item in lines
            ],
            groups=list(groups),
        )
        return QuoteRequest(quote_id=uuid4(), operation_id=uuid4(), customer_id=uuid4(), cart=cart)

    async def quote(self, command):
        self.quotes.add(command.quote_id)
        return await self.client.post(f"{ROOT}/quotes", json=command.model_dump(mode="json"))

    async def reserve(self, command, **changes):
        body = {
            "operation_id": str(command.operation_id),
            "quote_id": str(command.quote_id),
            "customer_id": str(command.customer_id),
            "cart_fingerprint": command.cart.fingerprint(),
        }
        return await self.client.post(f"{ROOT}/reservations", json={**body, **changes})

    async def action(self, command, action=None, *, customer_id=None):
        url = f"{ROOT}/reservations/{command.operation_id}"
        params = {"customer_id": str(customer_id or command.customer_id)}
        if action is None:
            return await self.client.get(url, params=params)
        return await self.client.post(f"{url}/{action}", params=params)

    async def stock(self, variant_id):
        async with self.database.sessions() as db:
            return (
                await db.execute(
                    select(VariantRow.on_hand, VariantRow.reserved).where(
                        VariantRow.id == variant_id
                    )
                )
            ).one()


@pytest.fixture
async def checkout(monkeypatch):
    database = Database(Settings())

    class TestAuthorization:
        async def check_checkout(self, authorization, scope):
            assert authorization == "Bearer integration-test"

    monkeypatch.setattr(app.state, "database", database, raising=False)
    monkeypatch.setattr(app.state, "authorization", TestAuthorization(), raising=False)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://catalog.test",
        headers={"Authorization": "Bearer integration-test"},
    ) as client:
        fixture = Fixture(database, client)
        try:
            yield fixture
        finally:
            async with database.sessions() as db, db.begin():
                operations = select(ReservationRow.operation_id).where(
                    ReservationRow.quote_id.in_(fixture.quotes)
                )
                await db.execute(
                    delete(AllocationRow).where(AllocationRow.operation_id.in_(operations))
                )
                await db.execute(
                    delete(ReservationRow).where(ReservationRow.quote_id.in_(fixture.quotes))
                )
                await db.execute(delete(QuoteRow).where(QuoteRow.id.in_(fixture.quotes)))
                variants = select(VariantRow.id).where(VariantRow.product_id.in_(fixture.products))
                await db.execute(delete(OfferRow).where(OfferRow.variant_id.in_(variants)))
                await db.execute(
                    delete(VariantRow).where(VariantRow.product_id.in_(fixture.products))
                )
                await db.execute(delete(ProductRow).where(ProductRow.id.in_(fixture.products)))
            await database.engine.dispose()


def code(response, status=409):
    assert response.status_code == status, response.text
    return response.json()["error"]["code"]


async def test_one_unit_twenty_concurrent_checkouts_and_commit_replays(checkout):
    variant = await checkout.add(1)
    commands = [checkout.command([variant]) for _ in range(20)]
    responses = await asyncio.gather(*(checkout.quote(command) for command in commands))
    assert all(response.is_success for response in responses)
    replies = await asyncio.gather(*(checkout.reserve(command) for command in commands))
    accepted = [
        command for command, reply in zip(commands, replies, strict=True) if reply.is_success
    ]
    assert len(accepted) == 1
    assert sum(reply.status_code == 409 for reply in replies) == 19
    assert all(code(reply) == "inventory.insufficient_stock" for reply in replies if reply.is_error)
    assert await checkout.stock(variant) == (1, 1)
    winner = accepted[0]
    assert (await checkout.action(winner)).json()["state"] == "held"
    assert code(await checkout.action(winner, customer_id=uuid4()), 404) == "reservation.not_found"
    replies = await asyncio.gather(*(checkout.reserve(winner) for _ in range(4)))
    assert all(reply.json()["state"] == "held" for reply in replies)
    replies = await asyncio.gather(*(checkout.action(winner, "commit") for _ in range(4)))
    assert all(reply.json()["state"] == "committed" for reply in replies)
    assert (await checkout.reserve(winner)).json()["state"] == "committed"
    assert code(await checkout.action(winner, "release")) == "reservation.state_conflict"
    assert await checkout.stock(variant) == (0, 0)


async def test_lost_stock_leaves_all_other_lines_untouched(checkout):
    available, contested = await checkout.add(4), await checkout.add(1)
    cart, winner = checkout.command([available, contested]), checkout.command([contested])
    assert (await checkout.quote(cart)).is_success
    assert (await checkout.quote(winner)).is_success
    assert (await checkout.reserve(winner)).is_success
    assert code(await checkout.reserve(cart)) == "inventory.insufficient_stock"
    assert await checkout.stock(available) == (4, 0)
    assert code(await checkout.action(cart), 404) == "reservation.not_found"
    for _ in range(2):
        assert (await checkout.action(winner, "release")).json()["state"] == "released"
    assert await checkout.stock(contested) == (1, 0)


@pytest.mark.parametrize(
    ("changed", "error"),
    [
        ("price", "quote.price_changed"),
        ("spec", "build.validation_stale"),
        ("selection", "build.selection_changed"),
        ("eligibility", "quote.eligibility_changed"),
        ("expiry", "quote.expired"),
        ("rules", "build.validation_stale"),
    ],
)
async def test_reserve_rejects_stale_quote(checkout, monkeypatch, changed, error):
    from nivaro_catalog.domain import evaluation

    variant = await checkout.add(4)
    group = CartGroup(
        id=uuid4(), version=1, mode="parts_only", name="PC", requires_dedicated_gpu=False
    )
    line = CartLine(
        id=uuid4(), version=1, variant_id=variant, group_id=group.id, slot_key="cpu", quantity=1
    )
    command = checkout.command([line], [group])
    assert (await checkout.quote(command)).is_success
    changes = {}
    async with checkout.database.sessions() as db, db.begin():
        offer = update(OfferRow).where(OfferRow.variant_id == variant, OfferRow.market == "ir")
        if changed == "price":
            await db.execute(offer.values(amount_minor=1200, price_version=2))
        elif changed == "spec":
            await db.execute(
                update(VariantRow).where(VariantRow.id == variant).values(spec_version=2)
            )
        elif changed == "eligibility":
            await db.execute(offer.values(available_for_sale=False, price_version=2))
        elif changed == "expiry":
            row = await db.get(QuoteRow, command.quote_id)
            row.snapshot = {**row.snapshot, "expires_at": "2000-01-01T00:00:00Z"}
        elif changed == "rules":
            monkeypatch.setattr(evaluation, "RULESET_VERSION", "next-rules")
        else:
            changes["cart_fingerprint"] = "f" * 64
    assert code(await checkout.reserve(command, **changes)) == error
    assert await checkout.stock(variant) == (4, 0)


async def test_group_identities_and_finished_prebuilt_stock_are_isolated(checkout):
    cpu = await checkout.add(7)
    prebuilt = await checkout.add(2, Prebuilt(component_descriptions=[f"SKU-{cpu}"]))
    groups = [
        CartGroup(
            id=uuid4(), version=2, mode="parts_only", name=f"PC {i}", requires_dedicated_gpu=False
        )
        for i in range(2)
    ]
    lines = [
        CartLine(
            id=uuid4(), version=1, group_id=group.id, slot_key="cpu", variant_id=cpu, quantity=1
        )
        for group in groups
    ]
    command = checkout.command([*lines, cpu, prebuilt], groups, market="international")
    response = await checkout.quote(command)
    assert response.is_success, response.text
    quote = response.json()
    assert (quote["currency"], quote["subtotal_minor"]) == ("USD", 4 * 337)
    assert {line["id"] for line in quote["lines"]} == {str(line.id) for line in command.cart.lines}
    assert [item["status"] for item in quote["groups"]] == ["incomplete", "incomplete"]
    assert quote["groups"][0]["selection_hash"] == selection_hash(
        command.cart.evaluation_request(groups[0])
    )
    command.cart.lines.reverse()
    assert (await checkout.quote(command)).json() == quote
    assert (await checkout.reserve(command)).json()["state"] == "held"
    assert await checkout.stock(cpu) == (7, 3)
    assert await checkout.stock(prebuilt) == (2, 1)
    command.cart.version += 1
    assert code(await checkout.quote(command)) == "quote.conflicting_request"
    assert code(await checkout.reserve(command)) == "build.selection_changed"
    assert (await checkout.action(command, "commit")).json()["state"] == "committed"
    assert await checkout.stock(cpu) == (4, 0)
    assert await checkout.stock(prebuilt) == (1, 0)


async def test_complete_build_is_independently_validated(checkout, complete_build):
    request, variants = complete_build
    for variant in variants.values():
        await checkout.add(4, variant.specifications, variant_id=variant.id)
    group = CartGroup(
        id=uuid4(), version=1, mode="complete_build", name="PC", requires_dedicated_gpu=False
    )
    lines = [
        CartLine(
            id=uuid4(),
            version=1,
            group_id=group.id,
            slot_key=line.slot_key,
            variant_id=line.variant_id,
            quantity=line.quantity,
        )
        for line in request.selections
    ]
    blocked = checkout.command(lines[:1], [group])
    assert code(await checkout.quote(blocked)) == "build.not_compatible"
    full = checkout.command(lines, [group])
    result = await checkout.quote(full)
    assert result.is_success, result.text
    assert result.json()["groups"][0]["status"] == "compatible"
    assert (await checkout.reserve(full)).is_success


async def test_reference_offers_cannot_be_quoted(checkout):
    variant = await checkout.add(3, reference=True)
    assert code(await checkout.quote(checkout.command([variant]))) == "quote.eligibility_changed"
    assert await checkout.stock(variant) == (3, 0)


async def test_expiry_worker_and_commit_race_release_once(checkout):
    variant = await checkout.add(1)
    command = checkout.command([variant])
    assert (await checkout.quote(command)).is_success
    assert (await checkout.reserve(command)).is_success
    async with checkout.database.sessions() as db, db.begin():
        await db.execute(
            update(ReservationRow)
            .where(ReservationRow.operation_id == command.operation_id)
            .values(expires_at=func.clock_timestamp() - timedelta(seconds=1))
        )
    async with checkout.database.sessions() as db:
        result, _ = await asyncio.gather(checkout.action(command, "commit"), expire_one(db))
        assert result.json()["state"] == "expired"
        assert not await expire_one(db)
    assert (await checkout.reserve(command)).json()["state"] == "expired"
    assert await checkout.stock(variant) == (1, 0)
