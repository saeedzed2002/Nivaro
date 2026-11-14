"""Compare two private saved builds without editing either draft."""

import asyncio
from collections import Counter
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Request
from pydantic import BaseModel

from nivaro_cart.api.builds import BuildSelection, BuildView, build_view, find_build, selections_of
from nivaro_cart.api.errors import ERROR_RESPONSES
from nivaro_cart.api.ownership import SaleStatus, request_actor, resolve_owner, sale_status
from nivaro_cart.domain.errors import CommerceError
from nivaro_cart.domain.mutations import Market
from nivaro_cart.infrastructure.catalog import (
    Catalog,
    CatalogUnavailable,
    Evaluation,
    SelectionUnavailable,
    Summary,
)
from nivaro_cart.infrastructure.database import Database

router = APIRouter(prefix="/api/v1/builds", tags=["builds"], responses=ERROR_RESPONSES)
OPTIONAL_ROLES = {"monitor", "keyboard", "mouse", "audio", "chair", "desk", "accessory"}


class ComparedPart(BuildSelection):
    summary: Summary | None
    status: SaleStatus | Literal["catalog_unavailable"]


class ComparedSlot(BaseModel):
    slot_key: str
    left: ComparedPart | None
    right: ComparedPart | None
    different: bool


class ComparedBuild(BaseModel):
    build: BuildView
    evaluation: Evaluation | None
    evaluation_status: Literal["ready", "selection_unavailable", "catalog_unavailable"]
    known_components_minor: str | None
    known_peripherals_minor: str | None
    unpriced_slots: list[str]
    price_basis: Literal["catalog_display"] = "catalog_display"


class Comparison(BaseModel):
    market: Market
    currency: Literal["IRR", "USD"]
    left: ComparedBuild
    right: ComparedBuild
    slots: list[ComparedSlot]
    price_status: Literal["ready", "catalog_unavailable"]
    reserves_stock: Literal[False] = False


async def evaluation_for(
    catalog: Catalog, build: BuildView
) -> tuple[Evaluation | None, Literal["ready", "selection_unavailable", "catalog_unavailable"]]:
    try:
        return await catalog.evaluate(
            market=build.market,
            mode=build.mode,
            dedicated_gpu=build.requires_dedicated_gpu,
            selections=[
                (line.slot_key, line.variant_id, line.quantity) for line in build.selections
            ],
        ), "ready"
    except SelectionUnavailable:
        return None, "selection_unavailable"
    except CatalogUnavailable:
        return None, "catalog_unavailable"


async def price_book(
    catalog: Catalog, left: BuildView, right: BuildView
) -> dict[UUID, Summary | None] | None:
    try:
        return await catalog.summaries(
            [line.variant_id for line in [*left.selections, *right.selections]], left.market
        )
    except CatalogUnavailable:
        return None


def price_column(
    build: BuildView,
    evaluation: tuple[
        Evaluation | None, Literal["ready", "selection_unavailable", "catalog_unavailable"]
    ],
    prices: dict[UUID, Summary | None] | None,
) -> tuple[ComparedBuild, dict[str, ComparedPart]]:
    quantities: Counter[UUID] = Counter()
    for line in build.selections:
        quantities[line.variant_id] += line.quantity
    components = peripherals = None
    unpriced = []
    parts = {}
    for line in build.selections:
        summary = prices[line.variant_id] if prices is not None else None
        part = ComparedPart(
            **line.model_dump(),
            summary=summary,
            status="catalog_unavailable"
            if prices is None
            else sale_status(summary, quantities[line.variant_id]),
        )
        parts[line.slot_key] = part
        if summary is None or summary.offer is None:
            unpriced.append(line.slot_key)
        elif line.role in OPTIONAL_ROLES:
            peripherals = (peripherals or 0) + summary.offer.amount_minor * line.quantity
        else:
            components = (components or 0) + summary.offer.amount_minor * line.quantity
    result = ComparedBuild(
        build=build,
        evaluation=evaluation[0],
        evaluation_status=evaluation[1],
        known_components_minor=str(components) if components is not None else None,
        known_peripherals_minor=str(peripherals) if peripherals is not None else None,
        unpriced_slots=unpriced,
    )
    return result, parts


@router.get("/{build_id}/comparison")
async def compare_builds(build_id: UUID, other_id: UUID, request: Request) -> Comparison:
    if build_id == other_id:
        raise CommerceError("build.comparison_requires_distinct_drafts", 422)
    actor = await request_actor(request)
    database: Database = request.app.state.database
    async with database.sessions.begin() as db:
        owner = await resolve_owner(db, actor)
        first = await find_build(db, owner.id, build_id)
        second = await find_build(db, owner.id, other_id)
        if first.market != second.market or first.currency != second.currency:
            raise CommerceError("build.comparison_market_mismatch", 422)
        left = build_view(first, await selections_of(db, first))
        right = build_view(second, await selections_of(db, second))

    catalog: Catalog = request.app.state.catalog
    prices, left_evaluation, right_evaluation = await asyncio.gather(
        price_book(catalog, left, right),
        evaluation_for(catalog, left),
        evaluation_for(catalog, right),
    )
    left_column, left_parts = price_column(left, left_evaluation, prices)
    right_column, right_parts = price_column(right, right_evaluation, prices)
    slots = []
    for key in sorted(left_parts.keys() | right_parts.keys()):
        a, b = left_parts.get(key), right_parts.get(key)
        different = (
            a is None or b is None or (a.variant_id, a.quantity) != (b.variant_id, b.quantity)
        )
        slots.append(ComparedSlot(slot_key=key, left=a, right=b, different=different))
    return Comparison(
        market=left.market,
        currency=left.currency,
        left=left_column,
        right=right_column,
        slots=slots,
        price_status="catalog_unavailable" if prices is None else "ready",
    )
