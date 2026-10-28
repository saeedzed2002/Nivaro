import hmac
import ipaddress
import re
import secrets
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Annotated, cast
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, FastAPI, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response
from pwdlib import PasswordHash
from redis.asyncio import Redis
from redis.exceptions import RedisError
from sqlalchemy import func, select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from nivaro_identity.api.limits import BoundedBody
from nivaro_identity.api.schemas import (
    AddressEdit,
    AddressInput,
    AddressResponse,
    AdminLogin,
    ChallengeResponse,
    CSRFResponse,
    ErrorEnvelope,
    Logout,
    Phone,
    Profile,
    ProfileEdit,
    SessionResponse,
    VerifyCode,
)
from nivaro_identity.domain.errors import IdentityError
from nivaro_identity.domain.security import SessionKind, Tokens, authenticate_value, digest
from nivaro_identity.infrastructure.database import Database
from nivaro_identity.infrastructure.models import Address, Administrator, Session, User
from nivaro_identity.infrastructure.otp import OTP, RateLimited
from nivaro_identity.infrastructure.sessions import Authenticated, Issued, Sessions
from nivaro_identity.settings import Settings

passwords = PasswordHash.recommended()


async def database(request: Request) -> AsyncIterator[AsyncSession]:
    async with request.app.state.database.sessions() as db:
        yield db


DB = Annotated[AsyncSession, Depends(database)]


def kind_for(request: Request) -> SessionKind:
    return "admin" if request.url.path.startswith("/api/v1/admin/") else "customer"


def cookie_names(kind: SessionKind) -> tuple[str, str]:
    return f"nivaro_{kind}_access", f"nivaro_{kind}_refresh"


def refresh_path(kind: SessionKind) -> str:
    return "/api/v1/admin/auth/refresh" if kind == "admin" else "/api/v1/auth/refresh"


def set_cookies(response: Response, issued: Issued, kind: SessionKind, settings: Settings) -> None:
    access, refresh = cookie_names(kind)
    seconds = max(0, int((issued.session.expires_at - datetime.now(UTC)).total_seconds()))
    secure = settings.environment == "release"
    response.set_cookie(
        access,
        issued.access,
        max_age=min(300, seconds),
        path="/",
        httponly=True,
        secure=secure,
        samesite="lax",
    )
    response.set_cookie(
        refresh,
        issued.refresh,
        max_age=seconds,
        path=refresh_path(kind),
        httponly=True,
        secure=secure,
        samesite="strict",
    )


def origin(request: Request) -> None:
    if request.headers.get("origin") not in request.app.state.settings.allowed_origins:
        raise IdentityError("origin.forbidden", 403)


def csrf_read_origin(request: Request) -> None:
    # The custom header forces a preflight cross-origin; this app grants no CORS.
    if (
        request.headers.get("x-csrf-request") != "1"
        or request.headers.get("sec-fetch-site") == "cross-site"
    ):
        raise IdentityError("origin.forbidden", 403)
    if (
        request.headers.get("origin")
        and request.headers["origin"] not in request.app.state.settings.allowed_origins
    ):
        raise IdentityError("origin.forbidden", 403)


def client_ip(request: Request) -> str:
    raw = request.client.host if request.client else "unknown"
    if request.app.state.settings.trust_gateway_client_ip:
        raw = request.headers.get("x-nivaro-client-ip", raw)
    try:
        return str(ipaddress.ip_address(raw))
    except ValueError:
        return "unknown"


async def authenticated(request: Request, db: DB) -> Authenticated:
    kind = kind_for(request)
    auth = await request.app.state.sessions.authenticate(
        db,
        request.cookies.get(cookie_names(kind)[0], ""),
        kind,
        lock=request.method not in {"GET", "HEAD"},
    )
    if request.method not in {"GET", "HEAD"}:
        request.app.state.sessions.check_csrf(auth.session, request.headers.get("x-csrf-token", ""))
    return cast(Authenticated, auth)


Auth = Annotated[Authenticated, Depends(authenticated)]


def session_response(auth: Authenticated, sessions: Sessions) -> SessionResponse:
    return SessionResponse(
        profile=Profile(id=auth.user.id, name=auth.user.name, phone=auth.user.phone),
        permissions=auth.permissions,
        expires_at=auth.session.expires_at,
        csrf_token=sessions.csrf(auth.session),
    )


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.settings = settings
        app.state.database = Database(settings)
        redis = Redis(
            host=settings.redis_host,
            port=settings.redis_port,
            password=settings.secret(settings.redis_password_file),
            decode_responses=True,
            socket_connect_timeout=2,
            socket_timeout=2,
        )
        app.state.redis = redis
        pepper = settings.secret(settings.otp_pepper_file)
        app.state.otp = OTP(redis, pepper, settings.otp_ip_limit)
        app.state.sessions = Sessions(Tokens(settings), pepper)
        app.state.dummy_password = await run_in_threadpool(
            passwords.hash, secrets.token_urlsafe(48)
        )
        try:
            yield
        finally:
            await redis.aclose()
            await app.state.database.engine.dispose()

    app = FastAPI(
        title="Nivaro Identity",
        version="0.3.0",
        lifespan=lifespan,
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )

    def error(
        request: Request, status: int, code: str, retry_after: int | None = None
    ) -> JSONResponse:
        headers = {"Cache-Control": "no-store"}
        if retry_after:
            headers["Retry-After"] = str(retry_after)
        return JSONResponse(
            {
                "error": {
                    "code": code,
                    "request_id": getattr(request.state, "request_id", str(uuid4())),
                }
            },
            status_code=status,
            headers=headers,
        )

    @app.middleware("http")
    async def security(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        candidate = request.headers.get("x-request-id", "")
        request.state.request_id = (
            candidate if re.fullmatch("[A-Za-z0-9_-]{1,64}", candidate) else str(uuid4())
        )
        if request.method not in {"GET", "HEAD", "OPTIONS"}:
            try:
                origin(request)
            except IdentityError:
                return error(request, 403, "origin.forbidden")
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Request-ID"] = request.state.request_id
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response

    @app.exception_handler(IdentityError)
    async def identity_error(request: Request, exc: IdentityError) -> JSONResponse:
        return error(request, exc.status, exc.code, exc.retry_after)

    @app.exception_handler(RateLimited)
    async def rate_error(request: Request, exc: RateLimited) -> JSONResponse:
        return error(request, 429, "login.rate_limited", exc.retry_after)

    @app.exception_handler(RequestValidationError)
    async def invalid(request: Request, exc: RequestValidationError) -> JSONResponse:
        return error(request, 422, "request.invalid")

    @app.exception_handler(SQLAlchemyError)
    @app.exception_handler(RedisError)
    async def unavailable(request: Request, exc: Exception) -> JSONResponse:
        return error(request, 503, "identity.unavailable")

    @app.get("/health/live", include_in_schema=False)
    async def live() -> dict[str, str]:
        return {"status": "ok", "service": "identity"}

    @app.get("/health/ready", include_in_schema=False)
    async def ready(db: DB) -> dict[str, str]:
        if await db.scalar(text("SELECT version_num FROM alembic_version")) != "0001_identity":
            raise IdentityError("identity.schema", 503)
        await app.state.redis.ping()
        return {"status": "ok", "service": "identity"}

    @app.get("/.well-known/jwks.json")
    async def keys() -> dict[str, list[dict[str, object]]]:
        return cast(dict[str, list[dict[str, object]]], app.state.sessions.tokens.public_keys())

    router = APIRouter(
        prefix="/api/v1",
        responses={status: {"model": ErrorEnvelope} for status in (401, 403, 409, 422, 429, 503)},
    )

    @router.post("/auth/otp/request", operation_id="requestCode")
    async def request_code(data: Phone, request: Request) -> ChallengeResponse:
        if settings.otp_provider != "mock":
            raise IdentityError("delivery.unavailable", 503)
        challenge = await app.state.otp.request(data.phone, client_ip(request))
        return ChallengeResponse(
            challenge_id=challenge.id,
            development_code=challenge.code if data.phone in settings.mock_phones else None,
        )

    @router.post("/auth/otp/verify", operation_id="verifyCode")
    async def verify_code(data: VerifyCode, response: Response, db: DB) -> SessionResponse:
        valid = await app.state.otp.verify(data.phone, str(data.challenge_id), data.code)
        if not valid or settings.otp_provider != "mock" or data.phone not in settings.mock_phones:
            raise IdentityError("login.invalid")
        sessions: Sessions = app.state.sessions
        user = await sessions.customer(db, data.phone)
        issued = await sessions.issue(db, user, "customer")
        await db.commit()
        set_cookies(response, issued, "customer", settings)
        return session_response(Authenticated(user, issued.session, []), sessions)

    @router.post("/admin/auth/login", operation_id="adminLogin")
    async def admin_login(
        data: AdminLogin, request: Request, response: Response, db: DB
    ) -> SessionResponse:
        email = str(data.email).strip().lower()
        pepper = app.state.otp.pepper
        keys = [
            "identity:admin-limit:" + authenticate_value(pepper, purpose, value)
            for purpose, value in (("email", email), ("ip", client_ip(request)))
        ]
        limited = await app.state.redis.eval(
            "local blocked=0; for i=1,2 do local n=redis.call('INCR',KEYS[i]); if n==1 then redis.call('EXPIRE',KEYS[i],900) end; if n>tonumber(ARGV[i]) then blocked=1 end end; return blocked",
            2,
            *keys,
            5,
            30,
        )
        if limited:
            raise RateLimited(900)
        admin = await db.scalar(select(Administrator).where(Administrator.email == email))
        encoded = admin.password_hash if admin else app.state.dummy_password
        valid = await run_in_threadpool(passwords.verify, data.password, encoded)
        if not valid or admin is None:
            raise IdentityError("login.invalid")
        user = await db.scalar(select(User).where(User.id == admin.user_id).with_for_update())
        # Re-read credentials under the user lock; a password change must win.
        current = await db.get(Administrator, admin.user_id, populate_existing=True)
        if (
            user is None
            or current is None
            or not hmac.compare_digest(encoded, current.password_hash)
        ):
            raise IdentityError("login.invalid")
        sessions: Sessions = app.state.sessions
        issued = await sessions.issue(db, user, "admin")
        permissions = await sessions.permissions(db, user, "admin")
        await db.commit()
        set_cookies(response, issued, "admin", settings)
        return session_response(Authenticated(user, issued.session, permissions), sessions)

    # Distinct route IDs and cookie kinds; all handlers derive kind from fixed
    # server paths, never a client-provided role/kind parameter.
    for kind in ("customer", "admin"):
        prefix = "/admin/auth" if kind == "admin" else "/auth"

        async def current(request: Request, auth: Auth) -> SessionResponse:
            return session_response(auth, app.state.sessions)

        async def csrf_token(request: Request, auth: Auth) -> CSRFResponse:
            csrf_read_origin(request)
            return CSRFResponse(csrf_token=app.state.sessions.csrf(auth.session))

        async def refresh_csrf(request: Request, db: DB) -> CSRFResponse:
            csrf_read_origin(request)
            kind = kind_for(request)
            raw = request.cookies.get(cookie_names(kind)[1], "")
            session = await db.scalar(
                select(Session).where(Session.refresh_hash == digest(raw), Session.kind == kind)
            )
            if session is None or session.revoked_at or session.expires_at <= datetime.now(UTC):
                raise IdentityError("session.invalid")
            user = await db.get(User, session.user_id)
            if user is None:
                raise IdentityError("session.invalid")
            await app.state.sessions.permissions(db, user, kind)
            return CSRFResponse(csrf_token=app.state.sessions.csrf(session))

        async def refresh(request: Request, response: Response, db: DB) -> CSRFResponse:
            kind = kind_for(request)
            issued = await app.state.sessions.refresh(
                db,
                request.cookies.get(cookie_names(kind)[1], ""),
                request.headers.get("x-csrf-token", ""),
                kind,
            )
            await db.commit()
            set_cookies(response, issued, kind, settings)
            return CSRFResponse(csrf_token=issued.csrf)

        async def logout(
            data: Logout, request: Request, response: Response, db: DB, auth: Auth
        ) -> dict[str, bool]:
            await app.state.sessions.revoke(db, auth, data.all_devices)
            await db.commit()
            kind = kind_for(request)
            access, refresh = cookie_names(kind)
            response.delete_cookie(access, path="/")
            response.delete_cookie(refresh, path=refresh_path(kind))
            return {"logged_out": True}

        router.add_api_route(
            prefix + "/session", current, methods=["GET"], operation_id=kind + "Session"
        )
        router.add_api_route(
            prefix + "/csrf", csrf_token, methods=["GET"], operation_id=kind + "Csrf"
        )
        router.add_api_route(
            prefix + "/refresh/csrf",
            refresh_csrf,
            methods=["GET"],
            operation_id=kind + "RefreshCsrf",
        )
        router.add_api_route(
            prefix + "/refresh", refresh, methods=["POST"], operation_id=kind + "Refresh"
        )
        router.add_api_route(
            prefix + "/logout", logout, methods=["POST"], operation_id=kind + "Logout"
        )

    @router.get("/me", operation_id="getProfile")
    async def profile(auth: Auth) -> Profile:
        return Profile(id=auth.user.id, name=auth.user.name, phone=auth.user.phone)

    @router.patch("/me", operation_id="editProfile")
    async def edit_profile(data: ProfileEdit, db: DB, auth: Auth) -> Profile:
        auth.user.name = data.name
        await db.commit()
        return Profile(id=auth.user.id, name=auth.user.name, phone=auth.user.phone)

    @router.get("/me/addresses", operation_id="listAddresses")
    async def addresses(db: DB, auth: Auth) -> list[AddressResponse]:
        values = await db.scalars(
            select(Address).where(Address.user_id == auth.user.id).order_by(Address.id)
        )
        return [AddressResponse.model_validate(value) for value in values]

    @router.post("/me/addresses", operation_id="createAddress", status_code=201)
    async def add_address(data: AddressInput, db: DB, auth: Auth) -> AddressResponse:
        if (
            await db.scalar(
                select(func.count()).select_from(Address).where(Address.user_id == auth.user.id)
            )
            or 0
        ) >= 20:
            raise IdentityError("address.limit", 409)
        address = Address(user_id=auth.user.id, **data.model_dump())
        db.add(address)
        await db.commit()
        return AddressResponse.model_validate(address)

    @router.put("/me/addresses/{address_id}", operation_id="editAddress")
    async def edit_address(
        address_id: UUID, data: AddressEdit, db: DB, auth: Auth
    ) -> AddressResponse:
        address = await db.scalar(
            select(Address).where(Address.id == address_id, Address.user_id == auth.user.id)
        )
        if address is None:
            raise IdentityError("address.not_found", 404)
        if address.version != data.version:
            raise IdentityError("address.changed", 409)
        for key, value in data.model_dump(exclude={"version"}).items():
            setattr(address, key, value)
        address.version += 1
        await db.commit()
        return AddressResponse.model_validate(address)

    @router.delete("/me/addresses/{address_id}", operation_id="deleteAddress", status_code=204)
    async def delete_address(
        address_id: UUID, db: DB, auth: Auth, version: Annotated[int, Query(ge=1)]
    ) -> Response:
        address = await db.scalar(
            select(Address).where(Address.id == address_id, Address.user_id == auth.user.id)
        )
        if address is None:
            raise IdentityError("address.not_found", 404)
        if address.version != version:
            raise IdentityError("address.changed", 409)
        await db.delete(address)
        await db.commit()
        return Response(status_code=204)

    app.include_router(router)
    app.add_middleware(BoundedBody, max_bytes=16384)
    return app


app = create_app()
