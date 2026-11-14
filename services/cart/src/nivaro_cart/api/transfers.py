"""Review a saved configuration against current catalog facts and copy it atomically."""

import asyncio
import hashlib
import json
from collections import Counter
from itertools import chain
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Header, Request
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from nivaro_cart.api.builds import BuildSelection, BuildView, build_view, find_build, selections_of
from nivaro_cart.api.errors import ERROR_RESPONSES
from nivaro_cart.api.items import Positive
from nivaro_cart.api.ownership import SaleStatus, request_actor, resolve_owner, sale_status
from nivaro_cart.domain.errors import CommerceError
from nivaro_cart.domain.limits import validate_quantities
from nivaro_cart.domain.mutations import CartConflict
from nivaro_cart.domain.ownership import owned_cart
from nivaro_cart.infrastructure.catalog import (
    Catalog,
    CatalogUnavailable,
    Digest,
    Evaluation,
    SelectionUnavailable,
    Summary,
)
from nivaro_cart.infrastructure.database import Database
from nivaro_cart.infrastructure.models import Cart, CartGroup, CartLine, Operation

router = APIRouter(prefix="/api/v1/builds", tags=["builds"], responses=ERROR_RESPONSES)


class ReviewLine(BuildSelection):
    summary: Summary | None
    status: SaleStatus


class BuildReview(BaseModel):
    build: BuildView
    cart_id: UUID
    cart_version: int
    evaluation: Evaluation | None
    lines: list[ReviewLine]
    blocker: str | None
    review_digest: Digest | None
    reserves_stock: Literal[False] = False


class TransferRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_build_version: Positive
    expected_cart_version: Positive
    review_digest: Digest


class TransferReceipt(BaseModel):
    cart_id: UUID
    group_id: UUID
    cart_version: int
    group_version: int
    reserves_stock: Literal[False] = False


async def cart_lines(db: AsyncSession, cart: Cart) -> list[CartLine]:
    return list(await db.scalars(select(CartLine).where(CartLine.cart_id == cart.id)))


async def review_build(
    catalog: Catalog,
    build: BuildView,
    cart: Cart,
    existing: list[CartLine],
    *,
    purpose: Literal["transfer", "group_edit"] = "transfer",
) -> BuildReview:
    quantities: Counter[UUID] = Counter()
    for variant_id, quantity in chain(
        ((line.variant_id, line.quantity) for line in existing),
        ((line.variant_id, line.quantity) for line in build.selections),
    ):
        quantities[variant_id] += quantity

    async def evaluate() -> Evaluation | None:
        try:
            return await catalog.evaluate(
                market=build.market,
                mode=build.mode,
                dedicated_gpu=build.requires_dedicated_gpu,
                selections=[
                    (line.slot_key, line.variant_id, line.quantity) for line in build.selections
                ],
            )
        except SelectionUnavailable:
            return None

    try:
        # TaskGroup would wrap upstream errors; gather's API keeps the existing
        # error contract. Both gateway calls have their own bounded deadline.
        summaries, evaluation = await asyncio.gather(
            catalog.summaries([line.variant_id for line in build.selections], build.market),
            evaluate(),
        )
    except CatalogUnavailable as exc:
        raise CommerceError("catalog.unavailable", 503) from exc

    lines = [
        ReviewLine(
            **line.model_dump(),
            summary=summaries[line.variant_id],
            status=sale_status(summaries[line.variant_id], quantities[line.variant_id]),
        )
        for line in build.selections
    ]
    blocker = None
    if not lines:
        blocker = "build.empty"
    elif any(line.status != "available" for line in lines):
        blocker = "build.items_unavailable"
    elif evaluation is None:
        blocker = "build.selection_unavailable"
    elif build.mode == "complete_build" and evaluation.status != "compatible":
        blocker = "build.compatibility_required"

    review_digest = None
    if blocker is None:
        assert evaluation is not None
        prices = []
        for line in lines:
            assert line.summary is not None and line.summary.offer is not None
            offer = line.summary.offer
            prices.append(
                (line.slot_key, str(line.variant_id), offer.amount_minor, offer.price_version)
            )
        reviewed = {
            "build": build.model_dump(mode="json"),
            "cart": str(cart.id),
            "cart_version": cart.version,
            "evaluation": evaluation.model_dump(mode="json", exclude={"evaluated_at"}),
            "prices": prices,
        }
        # Preserve the existing transfer fingerprint for in-flight reviews.
        review_digest = digest(reviewed if purpose == "transfer" else {"group_edit": reviewed})
    return BuildReview(
        build=build,
        cart_id=cart.id,
        cart_version=cart.version,
        evaluation=evaluation,
        lines=lines,
        blocker=blocker,
        review_digest=review_digest,
    )


def digest(payload: object) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


async def previous_transfer(
    db: AsyncSession, owner_id: UUID, key: str, fingerprint: str
) -> TransferReceipt | None:
    previous = await db.scalar(
        select(Operation).where(
            Operation.owner_id == owner_id,
            Operation.kind == "transfer",
            Operation.key == key,
        )
    )
    if previous is None:
        return None
    if previous.fingerprint != fingerprint:
        raise CommerceError("cart.idempotency_conflict")
    return TransferReceipt.model_validate(previous.result)


def require_cart_version(cart: Cart, version: int) -> None:
    if cart.version != version:
        raise CartConflict("cart.version_conflict", cart.version)


@router.get("/{build_id}/review")
async def get_build_review(build_id: UUID, request: Request) -> BuildReview:
    actor = await request_actor(request)
    database: Database = request.app.state.database
    async with database.sessions.begin() as db:
        owner = await resolve_owner(db, actor)
        build = await find_build(db, owner.id, build_id)
        view = build_view(build, await selections_of(db, build))
        cart = await owned_cart(db, owner, view.market)
        existing = await cart_lines(db, cart)
    return await review_build(request.app.state.catalog, view, cart, existing)


@router.post("/{build_id}/cart-transfers", status_code=201)
async def transfer_build(
    build_id: UUID,
    body: TransferRequest,
    request: Request,
    key: Annotated[
        str,
        Header(alias="Idempotency-Key", min_length=1, max_length=128, pattern=r"^[A-Za-z0-9_-]+$"),
    ],
) -> TransferReceipt:
    actor = await request_actor(request, mutating=True)
    database: Database = request.app.state.database
    fingerprint = digest({"build_id": str(build_id), **body.model_dump()})
    async with database.sessions.begin() as db:
        owner = await resolve_owner(db, actor, mutating=True)
        previous = await previous_transfer(db, owner.id, key, fingerprint)
        if previous is not None:
            return previous
        source = await find_build(db, owner.id, build_id, version=body.expected_build_version)
        view = build_view(source, await selections_of(db, source))
        cart = await owned_cart(db, owner, view.market)
        require_cart_version(cart, body.expected_cart_version)
        existing = await cart_lines(db, cart)

    review = await review_build(request.app.state.catalog, view, cart, existing)
    async with database.sessions.begin() as db:
        owner = await resolve_owner(db, actor, mutating=True)
        previous = await previous_transfer(db, owner.id, key, fingerprint)
        if previous is not None:
            return previous
        await find_build(db, owner.id, build_id, version=body.expected_build_version)
        cart = await owned_cart(db, owner, view.market)
        require_cart_version(cart, body.expected_cart_version)
        if review.blocker:
            raise CommerceError(review.blocker)
        if review.review_digest != body.review_digest:
            raise CommerceError("build.review_changed")
        validate_quantities(
            chain(
                ((line.variant_id, line.quantity) for line in existing),
                ((line.variant_id, line.quantity) for line in review.lines),
            ),
            request.app.state.settings.limits(),
        )
        group = CartGroup(
            cart_id=cart.id,
            name=view.name,
            mode=view.mode,
            requires_dedicated_gpu=view.requires_dedicated_gpu,
            source_build_id=view.id,
            source_build_version=view.version,
        )
        db.add(group)
        await db.flush()
        for line in review.lines:
            assert line.summary is not None and line.summary.offer is not None
            db.add(
                CartLine(
                    cart_id=cart.id,
                    group_id=group.id,
                    slot_key=line.slot_key,
                    variant_id=line.variant_id,
                    quantity=line.quantity,
                    observed_price_minor=line.summary.offer.amount_minor,
                    observed_price_version=line.summary.offer.price_version,
                )
            )
        cart.version += 1
        receipt = TransferReceipt(
            cart_id=cart.id,
            group_id=group.id,
            cart_version=cart.version,
            group_version=group.version,
        )
        db.add(
            Operation(
                owner_id=owner.id,
                kind="transfer",
                key=key,
                fingerprint=fingerprint,
                result=receipt.model_dump(mode="json"),
            )
        )
        return receipt
