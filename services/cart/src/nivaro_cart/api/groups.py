"""Review and replace an owned configuration group in one cart transaction."""

from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from nivaro_cart.api.builds import BuildContent, BuildView
from nivaro_cart.api.errors import ERROR_RESPONSES
from nivaro_cart.api.items import Positive
from nivaro_cart.api.ownership import GroupView, request_actor, resolve_owner
from nivaro_cart.api.transfers import ReviewLine, cart_lines, require_cart_version, review_build
from nivaro_cart.domain.errors import CommerceError
from nivaro_cart.domain.limits import Limits, validate_quantities
from nivaro_cart.domain.mutations import CartConflict, CartNotFound, Market
from nivaro_cart.domain.ownership import owned_cart
from nivaro_cart.infrastructure.catalog import Digest, Evaluation
from nivaro_cart.infrastructure.database import Database
from nivaro_cart.infrastructure.models import Cart, CartGroup, CartLine

router = APIRouter(prefix="/api/v1/cart/groups", tags=["cart"], responses=ERROR_RESPONSES)


class GroupEdit(BuildContent):
    market: Market
    expected_version: Positive
    expected_group_version: Positive


class ConfirmGroupEdit(GroupEdit):
    review_digest: Digest


class GroupEditReview(BaseModel):
    group_id: UUID
    cart_id: UUID
    cart_version: int
    group_version: int
    evaluation: Evaluation | None
    lines: list[ReviewLine]
    blocker: str | None
    review_digest: Digest | None
    reserves_stock: Literal[False] = False


class GroupEditReceipt(BaseModel):
    cart_id: UUID
    version: int
    group: GroupView
    reserves_stock: Literal[False] = False


async def find_group(
    db: AsyncSession, cart: Cart, group_id: UUID, expected_version: int
) -> CartGroup:
    group = await db.scalar(
        select(CartGroup).where(CartGroup.id == group_id, CartGroup.cart_id == cart.id)
    )
    if group is None:
        raise CartNotFound
    if group.version != expected_version:
        raise CartConflict("cart.group_version_conflict", group.version)
    return group


async def edit_review(group_id: UUID, body: GroupEdit, request: Request) -> GroupEditReview:
    actor = await request_actor(request, mutating=True)
    database: Database = request.app.state.database
    async with database.sessions.begin() as db:
        owner = await resolve_owner(db, actor, mutating=True)
        cart = await owned_cart(db, owner, body.market)
        require_cart_version(cart, body.expected_version)
        group = await find_group(db, cart, group_id, body.expected_group_version)
        other = [line for line in await cart_lines(db, cart) if line.group_id != group.id]
        # The shared review accepts a proposed configuration independently of
        # whether it came from a saved build or an existing cart group.
        proposed = BuildView(
            id=group.id,
            version=group.version,
            name=body.name,
            mode=body.mode,
            market=body.market,
            currency="IRR" if body.market == "ir" else "USD",
            requires_dedicated_gpu=body.requires_dedicated_gpu,
            selections=sorted(body.selections, key=lambda line: line.slot_key),
        )
    report = await review_build(
        request.app.state.catalog, proposed, cart, other, purpose="group_edit"
    )
    if report.blocker is None:
        limits: Limits = request.app.state.settings.limits()
        validate_quantities(
            [(line.variant_id, line.quantity) for line in other]
            + [(line.variant_id, line.quantity) for line in body.selections],
            limits,
        )
    return GroupEditReview(
        group_id=group_id,
        cart_id=cart.id,
        cart_version=cart.version,
        group_version=group.version,
        evaluation=report.evaluation,
        lines=report.lines,
        blocker=report.blocker,
        review_digest=report.review_digest,
    )


@router.post("/{group_id}/review")
async def review_group_edit(group_id: UUID, body: GroupEdit, request: Request) -> GroupEditReview:
    return await edit_review(group_id, body, request)


@router.patch("/{group_id}")
async def save_group_edit(
    group_id: UUID, body: ConfirmGroupEdit, request: Request
) -> GroupEditReceipt:
    review = await edit_review(group_id, body, request)
    if review.blocker:
        raise CommerceError(review.blocker)
    if review.review_digest != body.review_digest:
        raise CommerceError("build.review_changed")
    # A fresh session check after the catalog calls precedes the write.
    actor = await request_actor(request, mutating=True)
    database: Database = request.app.state.database
    async with database.sessions.begin() as db:
        owner = await resolve_owner(db, actor, mutating=True)
        cart = await owned_cart(db, owner, body.market)
        if cart.id != review.cart_id:
            raise CartNotFound
        require_cart_version(cart, body.expected_version)
        group = await find_group(db, cart, group_id, body.expected_group_version)
        existing = {
            line.slot_key: line for line in await cart_lines(db, cart) if line.group_id == group.id
        }
        for proposed in review.lines:
            assert proposed.summary is not None and proposed.summary.offer is not None
            offer = proposed.summary.offer
            line = existing.pop(proposed.slot_key, None)
            if line is None:
                db.add(
                    CartLine(
                        cart_id=cart.id,
                        group_id=group.id,
                        slot_key=proposed.slot_key,
                        variant_id=proposed.variant_id,
                        quantity=proposed.quantity,
                        observed_price_minor=offer.amount_minor,
                        observed_price_version=offer.price_version,
                    )
                )
            elif (
                line.variant_id,
                line.quantity,
                line.observed_price_minor,
                line.observed_price_version,
            ) != (
                proposed.variant_id,
                proposed.quantity,
                offer.amount_minor,
                offer.price_version,
            ):
                line.variant_id, line.quantity = proposed.variant_id, proposed.quantity
                line.observed_price_minor, line.observed_price_version = (
                    offer.amount_minor,
                    offer.price_version,
                )
                line.version += 1
        for omitted in existing.values():
            await db.delete(omitted)
        group.name, group.mode = body.name, body.mode
        group.requires_dedicated_gpu = body.requires_dedicated_gpu
        group.version += 1
        cart.version += 1
        return GroupEditReceipt(
            cart_id=cart.id, version=cart.version, group=GroupView.model_validate(group)
        )
