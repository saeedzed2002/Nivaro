"""Private cart state and guest-session bootstrap; commerce mutations follow later."""

from collections import Counter
from dataclasses import dataclass
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Request, Response
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from nivaro_cart.api.authorization import CustomerPrincipal, IdentityAuthorization
from nivaro_cart.api.errors import ERROR_RESPONSES
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
from nivaro_cart.infrastructure.catalog import Catalog, CatalogUnavailable, Summary
from nivaro_cart.infrastructure.database import Database
from nivaro_cart.infrastructure.models import CartGroup, CartLine, Owner
from nivaro_cart.settings import Settings

router = APIRouter(prefix="/api/v1/cart", tags=["cart"], responses=ERROR_RESPONSES)
SaleStatus = Literal[
    "available",
    "removed",
    "unpriced",
    "reference_only",
    "unavailable",
    "stock_unknown",
    "insufficient_stock",
]


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
    observed_price_minor: int | None
    observed_price_version: int | None
    summary: Summary | None = None
    status: SaleStatus | Literal["catalog_unavailable"] = "catalog_unavailable"
    price_changed: bool = False


class GroupView(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    name: str
    mode: Literal["complete_build", "parts_only"]
    requires_dedicated_gpu: bool
    version: int


class CartView(BaseModel):
    id: UUID
    market: Market
    currency: Literal["IRR", "USD"]
    version: int
    owner_scope: Literal["guest", "customer"]
    lines: list[LineView]
    groups: list[GroupView]
    catalog_status: Literal["ready", "unavailable"] = "ready"
    estimated_total_minor: str | None = None
    known_subtotal_minor: str = "0"
    reserves_stock: Literal[False] = False
    paid_cleanup_needs_review: bool = False


@dataclass(frozen=True)
class Actor:
    principal: CustomerPrincipal | None
    guest_cookie: str
    csrf: str


async def request_actor(request: Request, *, mutating: bool = False) -> Actor:
    settings: Settings = request.app.state.settings
    origin, csrf = request.headers.get("origin", ""), request.headers.get("x-csrf-token", "")
    if mutating and (
        origin not in settings.allowed_origins
        or not csrf
        or len(csrf) > 128
        or request.headers.get("sec-fetch-site") == "cross-site"
    ):
        raise AuthorizationError("auth.forbidden", 403)
    principal = None
    if "nivaro_customer_access" in request.cookies:
        authorization: IdentityAuthorization = request.app.state.authorization
        principal = await authorization.check(
            request.cookies["nivaro_customer_access"], mutating=mutating, origin=origin, csrf=csrf
        )
    return Actor(principal, request.cookies.get(GUEST_COOKIE, ""), csrf)


async def resolve_owner(db: AsyncSession, actor: Actor, *, mutating: bool = False) -> Owner:
    if actor.principal:
        return await customer_owner(db, actor.principal.user_id)
    return await guest_owner(db, actor.guest_cookie, csrf=actor.csrf if mutating else None)


def sale_status(summary: Summary | None, total_quantity: int) -> SaleStatus:
    if summary is None:
        return "removed"
    offer = summary.offer
    if offer is None:
        return "unpriced"
    if offer.reference_only:
        return "reference_only"
    if not offer.available_for_sale:
        return "unavailable"
    if summary.available_quantity is None:
        return "stock_unknown"
    if summary.available_quantity < total_quantity:
        return "insufficient_stock"
    return "available"


async def enrich(view: CartView, catalog: Catalog) -> CartView:
    try:
        summaries = await catalog.summaries([line.variant_id for line in view.lines], view.market)
    except CatalogUnavailable:
        view.catalog_status = "unavailable"
        return view
    totals: Counter[UUID] = Counter()
    for line in view.lines:
        totals[line.variant_id] += line.quantity
    subtotal, complete = 0, True
    for line in view.lines:
        summary = summaries[line.variant_id]
        line.summary = summary
        # Validated status vocabulary is also used by mutation sale checks.
        line.status = sale_status(summary, totals[line.variant_id])
        offer = summary.offer if summary else None
        if offer and line.observed_price_minor is not None:
            line.price_changed = (
                line.observed_price_minor != offer.amount_minor
                or line.observed_price_version != offer.price_version
            )
        if line.status == "available" and offer:
            subtotal += offer.amount_minor * line.quantity
        else:
            complete = False
    view.known_subtotal_minor = str(subtotal)
    view.estimated_total_minor = str(subtotal) if complete else None
    return view


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
async def guest_session(
    request: Request, response: Response, recover_expired: bool = False
) -> GuestSessionView:
    _guest_request(request, creating=True)
    database: Database = request.app.state.database
    raw = request.cookies.get(GUEST_COOKIE, "")
    async with database.sessions.begin() as db:
        owner = None
        if raw:
            try:
                owner = await guest_owner(db, raw)
            except AuthorizationError as exc:
                if not recover_expired or exc.code not in {"guest.expired", "guest.required"}:
                    raise
        if owner is None:
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
    actor = await request_actor(request)
    async with database.sessions.begin() as db:
        owner = await resolve_owner(db, actor)
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
            paid_cleanup_needs_review=cart.paid_cleanup_needs_review,
            id=cart.id,
            market=market,
            currency="IRR" if market == "ir" else "USD",
            version=cart.version,
            owner_scope="customer" if actor.principal else "guest",
            lines=[LineView.model_validate(line) for line in lines],
            groups=[GroupView.model_validate(group) for group in groups],
        )
    if actor.principal is None:
        _cookie(response, actor.guest_cookie, request.app.state.settings)
    # Never hold owner/cart row locks while awaiting another service.
    return await enrich(result, request.app.state.catalog)
