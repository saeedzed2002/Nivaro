"""Discover and merge the current browser's guest cart after customer login."""

from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Header, Request
from pydantic import BaseModel, ConfigDict
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from nivaro_cart.api.errors import ERROR_RESPONSES
from nivaro_cart.api.items import Positive
from nivaro_cart.api.ownership import request_actor
from nivaro_cart.domain.errors import AuthorizationError
from nivaro_cart.domain.merge import merge_carts
from nivaro_cart.domain.mutations import CartNotFound, Market
from nivaro_cart.domain.ownership import customer_owner, guest_owner
from nivaro_cart.infrastructure.database import Database
from nivaro_cart.infrastructure.models import Cart, CartGroup, CartLine, Owner

router = APIRouter(prefix="/api/v1/cart/merge", tags=["cart"], responses=ERROR_RESPONSES)


class MergeSource(BaseModel):
    cart_id: UUID
    version: int
    line_count: int
    group_count: int


class MergeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    market: Market
    guest_cart_id: UUID
    expected_guest_version: Positive
    expected_version: Positive


class MergeResult(BaseModel):
    cart_id: UUID
    version: int
    guest_version: int
    moved_groups: int
    moved_lines: int
    combined_lines: int
    reserves_stock: Literal[False] = False


async def source_cart(db: AsyncSession, owner: Owner, market: Market) -> Cart | None:
    return await db.scalar(
        select(Cart).where(Cart.owner_id == owner.id, Cart.market == market).with_for_update()
    )


@router.get("")
async def merge_source(request: Request, market: Market) -> MergeSource | None:
    actor = await request_actor(request)
    if actor.principal is None:
        raise AuthorizationError("auth.required", 401)
    if not actor.guest_cookie:
        return None
    database: Database = request.app.state.database
    async with database.sessions.begin() as db:
        guest = await guest_owner(db, actor.guest_cookie)
        source = await source_cart(db, guest, market)
        if source is None:
            return None
        lines = await db.scalar(
            select(func.count()).select_from(CartLine).where(CartLine.cart_id == source.id)
        )
        groups = await db.scalar(
            select(func.count()).select_from(CartGroup).where(CartGroup.cart_id == source.id)
        )
        if not lines and not groups:
            return None
        return MergeSource(
            cart_id=source.id,
            version=source.version,
            line_count=lines or 0,
            group_count=groups or 0,
        )


@router.post("")
async def merge_guest(
    body: MergeRequest,
    request: Request,
    key: Annotated[
        str,
        Header(alias="Idempotency-Key", min_length=1, max_length=128, pattern=r"^[A-Za-z0-9_-]+$"),
    ],
) -> MergeResult:
    actor = await request_actor(request, mutating=True)
    if actor.principal is None:
        raise AuthorizationError("auth.required", 401)
    database: Database = request.app.state.database
    async with database.sessions.begin() as db:
        customer = await customer_owner(db, actor.principal.user_id)
        guest = await guest_owner(db, actor.guest_cookie)
        source = await source_cart(db, guest, body.market)
        if source is None or source.id != body.guest_cart_id:
            raise CartNotFound
        result = await merge_carts(
            db,
            guest=guest,
            customer=customer,
            source=source,
            market=body.market,
            source_version=body.expected_guest_version,
            target_version=body.expected_version,
            key=key,
            limits=request.app.state.settings.limits(),
        )
        return MergeResult.model_validate(result)
