"""Private cart state and guest-session bootstrap; commerce mutations follow later."""

from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Request, Response
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select

from nivaro_cart.api.authorization import IdentityAuthorization
from nivaro_cart.domain.errors import AuthorizationError
from nivaro_cart.domain.mutations import Market
from nivaro_cart.domain.ownership import (
    GUEST_COOKIE,
    GUEST_LIFETIME,
    customer_owner,
    guest_owner,
    issue_guest,
    owned_cart,
)
from nivaro_cart.infrastructure.database import Database
from nivaro_cart.infrastructure.models import CartGroup, CartLine
from nivaro_cart.settings import Settings

router = APIRouter(prefix="/api/v1/cart", tags=["cart"])


class GuestSessionView(BaseModel):
    csrf_token: str
    scope: Literal["guest"] = "guest"


class LineView(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    group_id: UUID | None
    slot_key: str | None
    variant_id: UUID
    quantity: int
    version: int


class GroupView(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    name: str
    mode: Literal["complete_build", "parts_only"]
    version: int


class CartView(BaseModel):
    id: UUID
    market: Market
    currency: Literal["IRR", "USD"]
    version: int
    owner_scope: Literal["guest", "customer"]
    lines: list[LineView]
    groups: list[GroupView]


def _guest_request(request: Request, *, creating: bool) -> None:
    settings: Settings = request.app.state.settings
    origin = request.headers.get("origin", "")
    if (
        request.headers.get("x-csrf-request") != "1"
        or request.headers.get("sec-fetch-site") == "cross-site"
        or (origin and origin not in settings.allowed_origins)
        or (creating and origin not in settings.allowed_origins)
    ):
        raise AuthorizationError("origin.forbidden", 403)
    if "nivaro_customer_access" in request.cookies:
        raise AuthorizationError("guest.customer_active", 409)


def _cookie(response: Response, raw: str, settings: Settings) -> None:
    response.set_cookie(
        GUEST_COOKIE,
        raw,
        max_age=int(GUEST_LIFETIME.total_seconds()),
        httponly=True,
        secure=settings.environment == "release",
        samesite="lax",
        path="/",
    )


@router.post("/session")
async def guest_session(request: Request, response: Response) -> GuestSessionView:
    _guest_request(request, creating=True)
    database: Database = request.app.state.database
    raw = request.cookies.get(GUEST_COOKIE, "")
    async with database.sessions.begin() as db:
        if raw:
            owner = await guest_owner(db, raw)
        else:
            issued = await issue_guest(db)
            owner, raw = issued.owner, issued.cookie
        assert owner.guest_csrf is not None
        result = GuestSessionView(csrf_token=owner.guest_csrf)
    _cookie(response, raw, request.app.state.settings)
    return result


@router.get("/session")
async def guest_csrf(request: Request) -> GuestSessionView:
    _guest_request(request, creating=False)
    database: Database = request.app.state.database
    async with database.sessions.begin() as db:
        owner = await guest_owner(db, request.cookies.get(GUEST_COOKIE, ""))
        assert owner.guest_csrf is not None
        return GuestSessionView(csrf_token=owner.guest_csrf)


@router.get("")
async def cart_state(request: Request, response: Response, market: Market = "ir") -> CartView:
    database: Database = request.app.state.database
    principal = None
    if "nivaro_customer_access" in request.cookies:
        authorization: IdentityAuthorization = request.app.state.authorization
        principal = await authorization.check(
            request.cookies["nivaro_customer_access"], mutating=False, origin="", csrf=""
        )
    raw = request.cookies.get(GUEST_COOKIE, "")
    async with database.sessions.begin() as db:
        owner = (
            await customer_owner(db, principal.user_id) if principal else await guest_owner(db, raw)
        )
        cart = await owned_cart(db, owner, market)
        lines = list(
            await db.scalars(
                select(CartLine).where(CartLine.cart_id == cart.id).order_by(CartLine.id)
            )
        )
        groups = list(
            await db.scalars(
                select(CartGroup).where(CartGroup.cart_id == cart.id).order_by(CartGroup.id)
            )
        )
        result = CartView(
            id=cart.id,
            market=market,
            currency="IRR" if market == "ir" else "USD",
            version=cart.version,
            owner_scope="customer" if principal else "guest",
            lines=[LineView.model_validate(line) for line in lines],
            groups=[GroupView.model_validate(group) for group in groups],
        )
    if principal is None:
        _cookie(response, raw, request.app.state.settings)
    return result
