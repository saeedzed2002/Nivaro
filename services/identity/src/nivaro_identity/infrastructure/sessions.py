"""Authoritative session state; callers commit mutations before sending cookies.

Lock ordering is user -> session throughout login/refresh/revocation. Permission
checks use current credentials and database state, never just a signed JWT claim.
"""

import hmac
import secrets
from dataclasses import dataclass
from datetime import timedelta
from uuid import uuid4

import jwt
from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from nivaro_identity.domain.errors import IdentityError
from nivaro_identity.domain.security import (
    ROLE_PERMISSIONS,
    SessionKind,
    Tokens,
    authenticate_value,
    digest,
)
from nivaro_identity.infrastructure.models import (
    Administrator,
    Audit,
    ConsumedRefresh,
    Session,
    User,
    now,
)


@dataclass
class Authenticated:
    user: User
    session: Session
    permissions: list[str]


@dataclass(repr=False)
class Issued:
    access: str
    refresh: str
    csrf: str
    session: Session


class Sessions:
    def __init__(self, tokens: Tokens, pepper: str):
        self.tokens = tokens
        self.pepper = pepper

    def csrf(self, session: Session) -> str:
        return authenticate_value(self.pepper, "csrf", str(session.id), str(session.family_id))

    def check_csrf(self, session: Session, value: str) -> None:
        if not value or not hmac.compare_digest(digest(value), session.csrf_hash):
            raise IdentityError("csrf.invalid", 403)

    async def permissions(self, db: AsyncSession, user: User, kind: SessionKind) -> list[str]:
        if user.disabled:
            raise IdentityError("session.invalid")
        if kind == "customer":
            return []
        admin = await db.get(Administrator, user.id, populate_existing=True)
        if admin is None or admin.role not in ROLE_PERMISSIONS:
            raise IdentityError("session.invalid")
        return ROLE_PERMISSIONS[admin.role]

    async def customer(self, db: AsyncSession, phone: str) -> User:
        await db.execute(
            insert(User)
            .values(id=uuid4(), phone=phone)
            .on_conflict_do_nothing(index_elements=[User.phone])
        )
        return (await db.scalars(select(User).where(User.phone == phone).with_for_update())).one()

    async def issue(self, db: AsyncSession, user: User, kind: SessionKind) -> Issued:
        permissions = await self.permissions(db, user, kind)
        refresh = secrets.token_urlsafe(48)
        session = Session(
            id=uuid4(),
            user_id=user.id,
            family_id=uuid4(),
            kind=kind,
            refresh_hash=digest(refresh),
            csrf_hash="",
            created_at=now(),
            expires_at=now() + (timedelta(days=30) if kind == "customer" else timedelta(hours=12)),
        )
        csrf = self.csrf(session)
        session.csrf_hash = digest(csrf)
        db.add(session)
        db.add(Audit(user_id=user.id, event=f"{kind}.login"))
        await db.flush()
        return Issued(
            self.tokens.issue(user.id, session.id, kind, permissions, session.expires_at),
            refresh,
            csrf,
            session,
        )

    async def authenticate(
        self, db: AsyncSession, token: str, kind: SessionKind, *, lock: bool = False
    ) -> Authenticated:
        try:
            claims = self.tokens.verify(token, kind)
        except (jwt.InvalidTokenError, ValueError) as error:
            raise IdentityError("session.invalid") from error
        query = select(User).where(User.id == claims.sub)
        if lock:
            query = query.with_for_update()
        user = await db.scalar(query.execution_options(populate_existing=True))
        session = await db.get(Session, claims.sid, populate_existing=True)
        if (
            user is None
            or session is None
            or session.user_id != user.id
            or session.kind != kind
            or session.revoked_at
            or session.expires_at <= now()
        ):
            raise IdentityError("session.invalid")
        permissions = await self.permissions(db, user, kind)
        if claims.permissions != permissions:
            raise IdentityError("session.invalid")
        return Authenticated(user, session, permissions)

    async def refresh(self, db: AsyncSession, raw: str, csrf: str, kind: SessionKind) -> Issued:
        if not raw or len(raw) > 128:
            raise IdentityError("session.invalid")
        token_hash = digest(raw)
        session = await db.scalar(select(Session).where(Session.refresh_hash == token_hash))
        consumed = await db.get(ConsumedRefresh, token_hash)
        if session is None and consumed:
            session = await db.get(Session, consumed.session_id)
        if session is None or session.kind != kind:
            raise IdentityError("session.invalid")
        user = await db.scalar(
            select(User)
            .where(User.id == session.user_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        session = await db.scalar(
            select(Session)
            .where(Session.id == session.id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if user is None or session is None or session.revoked_at or session.expires_at <= now():
            raise IdentityError("session.invalid")
        permissions = await self.permissions(db, user, kind)
        self.check_csrf(session, csrf)
        if session.refresh_hash != token_hash:
            consumed = await db.get(ConsumedRefresh, token_hash, populate_existing=True)
            if consumed and now() - consumed.consumed_at <= timedelta(seconds=5):
                raise IdentityError("session.refresh_race", 409, 1)
            session.revoked_at = now()
            db.add(Audit(user_id=user.id, event=f"{kind}.refresh_reuse"))
            # Revocation must survive the error response (not rollback with it).
            await db.commit()
            raise IdentityError("session.invalid")
        refresh = secrets.token_urlsafe(48)
        db.add(ConsumedRefresh(token_hash=token_hash, session_id=session.id, consumed_at=now()))
        session.refresh_hash = digest(refresh)
        await db.flush()
        return Issued(
            self.tokens.issue(user.id, session.id, kind, permissions, session.expires_at),
            refresh,
            self.csrf(session),
            session,
        )

    async def revoke(
        self, db: AsyncSession, auth: Authenticated, all_devices: bool = False
    ) -> None:
        query = update(Session).where(
            Session.user_id == auth.user.id,
            Session.kind == auth.session.kind,
            Session.revoked_at.is_(None),
        )
        if not all_devices:
            query = query.where(Session.id == auth.session.id)
        await db.execute(query.values(revoked_at=now()))
        db.add(
            Audit(
                user_id=auth.user.id,
                event=f"{auth.session.kind}.logout_all"
                if all_devices
                else f"{auth.session.kind}.logout",
            )
        )
