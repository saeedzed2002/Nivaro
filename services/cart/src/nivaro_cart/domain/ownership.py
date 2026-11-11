"""Durable owner resolution. Caller owns the enclosing transaction.

Customer IDs must originate from the freshly verified identity principal.
Guest bearer cookies are random and only their SHA-256 digest is persisted.
Owner locks precede cart locks throughout mutations and future merges.
"""

import hashlib
import hmac
import re
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from nivaro_cart.domain.errors import AuthorizationError
from nivaro_cart.domain.mutations import Market
from nivaro_cart.infrastructure.models import Cart, Owner

GUEST_LIFETIME = timedelta(days=30)
GUEST_COOKIE = "nivaro_guest_cart"
_TOKEN = re.compile(r"[A-Za-z0-9_-]{43}")


@dataclass(frozen=True)
class GuestIssued:
    owner: Owner
    cookie: str


async def issue_guest(db: AsyncSession) -> GuestIssued:
    raw = secrets.token_urlsafe(32)
    owner = Owner(
        guest_digest=hashlib.sha256(raw.encode()).hexdigest(), guest_csrf=secrets.token_urlsafe(32)
    )
    db.add(owner)
    await db.flush()
    return GuestIssued(owner, raw)


async def guest_owner(db: AsyncSession, raw: str, *, csrf: str | None = None) -> Owner:
    if not _TOKEN.fullmatch(raw):
        raise AuthorizationError("guest.required", 401)
    owner = await db.scalar(
        select(Owner)
        .where(Owner.guest_digest == hashlib.sha256(raw.encode()).hexdigest())
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if owner is None:
        raise AuthorizationError("guest.required", 401)
    instant = datetime.now(UTC)
    if instant - owner.last_active_at >= GUEST_LIFETIME:
        raise AuthorizationError("guest.expired", 401)
    # Do not refresh activity or establish a token on a rejected mutation.
    if csrf is not None and (
        not owner.guest_csrf
        or not _TOKEN.fullmatch(csrf)
        or not hmac.compare_digest(owner.guest_csrf, csrf)
    ):
        raise AuthorizationError("auth.forbidden", 403)
    if owner.guest_csrf is None:
        owner.guest_csrf = secrets.token_urlsafe(32)
    owner.last_active_at = instant
    await db.flush()
    return owner


async def customer_owner(db: AsyncSession, customer_id: UUID) -> Owner:
    await db.execute(
        insert(Owner)
        .values(id=uuid4(), customer_id=customer_id)
        .on_conflict_do_nothing(index_elements=[Owner.customer_id])
    )
    owner = await db.scalar(
        select(Owner)
        .where(Owner.customer_id == customer_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    assert owner is not None
    owner.last_active_at = datetime.now(UTC)
    return owner


async def owned_cart(db: AsyncSession, owner: Owner, market: Market) -> Cart:
    # Every owner resolution above holds its owner row lock until commit.
    await db.execute(
        insert(Cart)
        .values(
            id=uuid4(),
            owner_id=owner.id,
            market=market,
            currency="IRR" if market == "ir" else "USD",
            version=1,
        )
        .on_conflict_do_nothing(constraint="cart_owner_market")
    )
    cart = await db.scalar(
        select(Cart)
        .where(Cart.owner_id == owner.id, Cart.market == market)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    assert cart is not None
    return cart
