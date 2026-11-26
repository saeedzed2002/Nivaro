"""Versioned commerce mutations. Catalog reads never reserve or decrement stock."""

from collections import Counter
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Query, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from nivaro_cart.api.errors import ERROR_RESPONSES
from nivaro_cart.api.ownership import Actor, request_actor, resolve_owner, sale_status
from nivaro_cart.domain.errors import CommerceError
from nivaro_cart.domain.mutations import (
    CartConflict,
    CartNotFound,
    Market,
    add_standalone,
    add_standalone_batch,
    change_line,
    delete_group,
)
from nivaro_cart.domain.ownership import owned_cart
from nivaro_cart.infrastructure.catalog import Catalog, CatalogUnavailable, Summary
from nivaro_cart.infrastructure.database import Database
from nivaro_cart.infrastructure.models import CartLine

router = APIRouter(prefix="/api/v1/cart", tags=["cart"], responses=ERROR_RESPONSES)
Positive = Annotated[int, Field(strict=True, gt=0, le=2_147_483_647)]


class AddItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    market: Market
    expected_version: Positive
    variant_id: UUID
    quantity: Positive


class BatchLine(BaseModel):
    model_config = ConfigDict(extra="forbid")
    variant_id: UUID
    quantity: Positive


class AddItems(BaseModel):
    model_config = ConfigDict(extra="forbid")
    market: Market
    expected_version: Positive
    items: list[BatchLine] = Field(min_length=1, max_length=32)


class EditItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    market: Market
    expected_version: Positive
    expected_group_version: Positive | None = None
    quantity: Positive


class MutationResult(BaseModel):
    cart_id: UUID
    version: int
    line_id: UUID | None = None
    reserves_stock: Literal[False] = False


async def preflight(
    request: Request, actor: Actor, market: Market, version: int, line_id: UUID | None = None
) -> CartLine | None:
    database: Database = request.app.state.database
    async with database.sessions.begin() as db:
        owner = await resolve_owner(db, actor, mutating=True)
        cart = await owned_cart(db, owner, market)
        if cart.version != version:
            raise CartConflict("cart.version_conflict", cart.version)
        if line_id is None:
            return None
        line = await db.scalar(
            select(CartLine).where(CartLine.cart_id == cart.id, CartLine.id == line_id)
        )
        if line is None:
            raise CartNotFound
        return line


async def require_summary(request: Request, variant_id: UUID, market: Market) -> Summary:
    catalog: Catalog = request.app.state.catalog
    try:
        result = (await catalog.summaries([variant_id], market))[variant_id]
    except CatalogUnavailable as exc:
        raise CommerceError("catalog.unavailable", 503) from exc
    status = sale_status(result, 1)
    if status != "available":
        raise CommerceError(f"cart.{status}")
    assert result is not None
    return result


async def stock_check(db: AsyncSession, cart_id: UUID, summary: Summary, increment: int) -> None:
    quantities = await db.scalars(
        select(CartLine.quantity).where(
            CartLine.cart_id == cart_id, CartLine.variant_id == summary.variant_id
        )
    )
    if (
        summary.available_quantity is None
        or sum(quantities) + increment > summary.available_quantity
    ):
        raise CommerceError("cart.insufficient_stock")


def observe(line: CartLine, summary: Summary) -> None:
    if line.observed_price_minor is None:
        assert summary.offer is not None
        line.observed_price_minor = summary.offer.amount_minor
        line.observed_price_version = summary.offer.price_version


@router.post("/items", status_code=201)
async def add_item(body: AddItem, request: Request) -> MutationResult:
    actor = await request_actor(request, mutating=True)
    await preflight(request, actor, body.market, body.expected_version)
    summary = await require_summary(request, body.variant_id, body.market)
    database: Database = request.app.state.database
    async with database.sessions.begin() as db:
        owner = await resolve_owner(db, actor, mutating=True)
        cart = await owned_cart(db, owner, body.market)
        if cart.version != body.expected_version:
            raise CartConflict("cart.version_conflict", cart.version)
        await stock_check(db, cart.id, summary, body.quantity)
        line = await add_standalone(
            db,
            owner_id=owner.id,
            market=body.market,
            expected_version=body.expected_version,
            variant_id=body.variant_id,
            quantity=body.quantity,
            limits=request.app.state.settings.limits(),
        )
        observe(line, summary)
        result = MutationResult(cart_id=cart.id, version=cart.version, line_id=line.id)
    return result


@router.post("/items/batch", status_code=201)
async def add_items(body: AddItems, request: Request) -> MutationResult:
    actor = await request_actor(request, mutating=True)
    await preflight(request, actor, body.market, body.expected_version)
    quantities: Counter[UUID] = Counter()
    for item in body.items:
        quantities[item.variant_id] += item.quantity
    catalog: Catalog = request.app.state.catalog
    try:
        summaries = await catalog.summaries(list(quantities), body.market)
    except CatalogUnavailable as exc:
        raise CommerceError("catalog.unavailable", 503) from exc

    database: Database = request.app.state.database
    async with database.sessions.begin() as db:
        owner = await resolve_owner(db, actor, mutating=True)
        cart = await owned_cart(db, owner, body.market)
        if cart.version != body.expected_version:
            raise CartConflict("cart.version_conflict", cart.version)
        allowed: dict[UUID, Summary] = {}
        for variant, quantity in quantities.items():
            summary = summaries.get(variant)
            status = sale_status(summary, quantity)
            if summary is None or status != "available":
                raise CommerceError(f"cart.{status}")
            await stock_check(db, cart.id, summary, quantity)
            allowed[variant] = summary
        added = await add_standalone_batch(
            db,
            owner_id=owner.id,
            market=body.market,
            expected_version=body.expected_version,
            quantities=dict(quantities),
            limits=request.app.state.settings.limits(),
        )
        for variant, line in added.items():
            observe(line, allowed[variant])
        result = MutationResult(cart_id=cart.id, version=cart.version)
    return result


@router.patch("/items/{line_id}")
async def edit_item(line_id: UUID, body: EditItem, request: Request) -> MutationResult:
    actor = await request_actor(request, mutating=True)
    before = await preflight(request, actor, body.market, body.expected_version, line_id)
    assert before is not None
    # Decreases remain possible during catalog outages or after product removal.
    summary = (
        await require_summary(request, before.variant_id, body.market)
        if body.quantity > before.quantity
        else None
    )
    database: Database = request.app.state.database
    async with database.sessions.begin() as db:
        owner = await resolve_owner(db, actor, mutating=True)
        cart = await owned_cart(db, owner, body.market)
        if cart.version != body.expected_version:
            raise CartConflict("cart.version_conflict", cart.version)
        if summary:
            await stock_check(db, cart.id, summary, body.quantity - before.quantity)
        await change_line(
            db,
            owner_id=owner.id,
            market=body.market,
            expected_version=body.expected_version,
            line_id=line_id,
            quantity=body.quantity,
            expected_group_version=body.expected_group_version,
            limits=request.app.state.settings.limits(),
        )
        if summary:
            current = await db.get(CartLine, line_id)
            assert current is not None
            observe(current, summary)
        result = MutationResult(cart_id=cart.id, version=cart.version, line_id=line_id)
    return result


@router.delete("/items/{line_id}")
async def remove_item(
    line_id: UUID,
    request: Request,
    expected_version: Annotated[int, Query(ge=1)],
    market: Market = "ir",
    expected_group_version: Annotated[int | None, Query(ge=1)] = None,
) -> MutationResult:
    actor = await request_actor(request, mutating=True)
    database: Database = request.app.state.database
    async with database.sessions.begin() as db:
        owner = await resolve_owner(db, actor, mutating=True)
        cart = await owned_cart(db, owner, market)
        await change_line(
            db,
            owner_id=owner.id,
            market=market,
            expected_version=expected_version,
            line_id=line_id,
            quantity=None,
            expected_group_version=expected_group_version,
            limits=request.app.state.settings.limits(),
        )
        result = MutationResult(cart_id=cart.id, version=cart.version, line_id=line_id)
    return result


@router.delete("/groups/{group_id}")
async def remove_group(
    group_id: UUID,
    request: Request,
    expected_version: Annotated[int, Query(ge=1)],
    expected_group_version: Annotated[int, Query(ge=1)],
    market: Market = "ir",
) -> MutationResult:
    actor = await request_actor(request, mutating=True)
    database: Database = request.app.state.database
    async with database.sessions.begin() as db:
        owner = await resolve_owner(db, actor, mutating=True)
        cart = await owned_cart(db, owner, market)
        await delete_group(
            db,
            owner_id=owner.id,
            market=market,
            expected_version=expected_version,
            group_id=group_id,
            expected_group_version=expected_group_version,
        )
        result = MutationResult(cart_id=cart.id, version=cart.version)
    return result
