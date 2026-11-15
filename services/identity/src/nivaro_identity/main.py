import asyncio
import hmac
import ipaddress
import re
import secrets
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Annotated, cast
from uuid import UUID, uuid4

import jwt
from fastapi import APIRouter, Depends, FastAPI, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, Response
from pwdlib import PasswordHash
from redis.asyncio import Redis
from redis.exceptions import RedisError
from sqlalchemy import func, select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from nivaro_identity import accounts
from nivaro_identity.api.internal import (
    CATALOG_CUSTOMER_CHECK_PATH,
    CATALOG_MODERATOR_CHECK_PATH,
    SUPPORT_CHECK_PATH,
    CartCheck,
    CartPrincipal,
    CatalogCheck,
    CatalogCustomerPrincipal,
    CatalogPrincipal,
    SupportCheck,
    SupportPrincipal,
    authenticate_cart,
    authenticate_catalog,
    authenticate_catalog_customer,
    authenticate_catalog_moderator,
    authenticate_support,
)
from nivaro_identity.api.limits import BoundedBody
from nivaro_identity.api.schemas import (
    AddressEdit,
    AddressInput,
    AddressResponse,
    AdminLogin,
    AvatarStatus,
    ChallengeResponse,
    CSRFResponse,
    ErrorEnvelope,
    Logout,
    Phone,
    Profile,
    ProfileEdit,
    SessionResponse,
    StaffProfile,
    VerifyCode,
)
from nivaro_identity.api.service_tokens import (
    CHECKOUT_CONTEXT_PATH,
    ORDERS_STAFF_CONTEXT_PATH,
    SERVICE_TOKEN_PATH,
)
from nivaro_identity.api.service_tokens import router as service_tokens_router
from nivaro_identity.domain.errors import IdentityError
from nivaro_identity.domain.security import SessionKind, Tokens, authenticate_value, digest
from nivaro_identity.infrastructure import avatars
from nivaro_identity.infrastructure.avatar_storage import MAX_UPLOAD_BYTES, MediaStorage
from nivaro_identity.infrastructure.database import Database
from nivaro_identity.infrastructure.models import Address, Administrator, AvatarJob, Session, User
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


async def account_manager(request: Request, db: DB) -> Authenticated:
    auth = await request.app.state.sessions.authenticate(
        db, request.cookies.get(cookie_names("admin")[0], ""), "admin"
    )
    if "users.manage" not in auth.permissions:
        raise IdentityError("permission.denied", 403)
    if request.method == "PATCH":
        await accounts.lock_account_changes(db)
        # The actor's state can change while waiting for an account-management transaction.
        auth = await authenticated(request, db)
        if "users.manage" not in auth.permissions:
            raise IdentityError("permission.denied", 403)
    return cast(Authenticated, auth)


AccountManager = Annotated[Authenticated, Depends(account_manager)]
AccountPageSize = Annotated[int, Query(ge=1, le=100)]


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
        app.state.catalog_service_key = (
            settings.secret(settings.catalog_service_key_file)
            if settings.catalog_service_key_file
            else None
        )
        app.state.cart_service_key = (
            settings.secret(settings.cart_service_key_file)
            if settings.cart_service_key_file
            else None
        )
        app.state.support_service_key = (
            settings.secret(settings.support_service_key_file)
            if settings.support_service_key_file
            else None
        )
        app.state.orders_client_secret = (
            settings.secret(settings.orders_client_secret_file)
            if settings.orders_client_secret_file
            else None
        )
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
        if request.method not in {"GET", "HEAD", "OPTIONS"} and request.url.path not in {
            "/internal/v1/catalog/admin-check",
            CATALOG_CUSTOMER_CHECK_PATH,
            CATALOG_MODERATOR_CHECK_PATH,
            SUPPORT_CHECK_PATH,
            "/internal/v1/cart/customer-check",
            SERVICE_TOKEN_PATH,
            CHECKOUT_CONTEXT_PATH,
            ORDERS_STAFF_CONTEXT_PATH,
        }:
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
        if (
            await db.scalar(text("SELECT version_num FROM alembic_version"))
            != "0003_identity_account_management"
        ):
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

    async def avatar_status(request: Request, db: DB, auth: Auth) -> AvatarStatus:
        kind = kind_for(request)
        slot = await avatars.get_slot(db, auth.user.id, kind)
        if slot is None:
            return AvatarStatus(version=0)
        job = await db.get(AvatarJob, slot.desired_job_id) if slot.desired_job_id else None
        return AvatarStatus(
            version=slot.version,
            active=slot.active_job_id,
            candidate=slot.desired_job_id,
            state=job.state if job else None,
            error_code=job.error_code if job else None,
        )

    async def upload_avatar(
        request: Request, db: DB, auth: Auth, version: Annotated[int, Query(ge=0)]
    ) -> AvatarStatus:
        owner, session_id = auth.user.id, auth.session.id
        kind = kind_for(request)
        await db.rollback()
        content = bytearray()
        try:
            async with asyncio.timeout(30):
                async for chunk in request.stream():
                    if len(content) + len(chunk) > MAX_UPLOAD_BYTES:
                        raise IdentityError("avatar.too_large", 413)
                    content.extend(chunk)
        except TimeoutError as exc:
            raise IdentityError("avatar.upload_timeout", 408) from exc
        if not content:
            raise IdentityError("avatar.empty", 422)
        job_id = uuid4()

        def store() -> None:
            media = MediaStorage(settings.media_private_root, settings.media_output_root)
            media.write_original(job_id, bytes(content))

        try:
            await run_in_threadpool(store)
        except OSError as exc:
            raise IdentityError("avatar.storage_unavailable", 503) from exc
        # Revalidate revocation and CSRF after I/O, then keep the user row locked through commit.
        verified = await authenticated(request, db)
        if verified.user.id != owner or verified.session.id != session_id:
            raise IdentityError("session.invalid")
        await avatars.update_slot(db, owner, kind, version, job_id)
        await db.commit()
        return await avatar_status(request, db, verified)

    async def remove_avatar(
        request: Request, db: DB, auth: Auth, version: Annotated[int, Query(ge=0)]
    ) -> AvatarStatus:
        await avatars.update_slot(db, auth.user.id, kind_for(request), version, None)
        await db.commit()
        return await avatar_status(request, db, auth)

    async def avatar_output(
        request: Request, db: DB, auth: Auth, asset_id: UUID, size: int
    ) -> FileResponse:
        slot = await avatars.get_slot(db, auth.user.id, kind_for(request))
        if not slot or slot.active_job_id != asset_id or size not in (128, 256):
            raise IdentityError("avatar.not_found", 404)
        job = await db.get(AvatarJob, asset_id)
        if not job or job.slot_id != slot.id or job.state != "ready" or not job.attempt_id:
            raise IdentityError("avatar.not_found", 404)
        path = settings.media_output_root / job.attempt_id.hex / f"{size}.webp"
        if not path.is_file():
            raise IdentityError("avatar.not_found", 404)
        return FileResponse(
            path,
            media_type="image/webp",
            headers={"Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"},
        )

    for owner_prefix, scope in (("/me/avatar", "customer"), ("/admin/me/avatar", "staff")):
        router.add_api_route(
            owner_prefix, avatar_status, methods=["GET"], operation_id=scope + "Avatar"
        )
        router.add_api_route(
            owner_prefix,
            upload_avatar,
            methods=["PUT"],
            status_code=202,
            operation_id=scope + "UploadAvatar",
            openapi_extra={
                "requestBody": {
                    "required": True,
                    "content": {
                        "application/octet-stream": {
                            "schema": {"type": "string", "format": "binary"}
                        }
                    },
                }
            },
        )
        router.add_api_route(
            owner_prefix, remove_avatar, methods=["DELETE"], operation_id=scope + "RemoveAvatar"
        )
        router.add_api_route(
            owner_prefix + "/{asset_id}/{size}",
            avatar_output,
            methods=["GET"],
            operation_id=scope + "AvatarOutput",
            response_class=FileResponse,
        )

    @router.get("/admin/me", operation_id="readStaffProfile")
    async def staff_profile(db: DB, auth: Auth) -> StaffProfile:
        admin = await db.get(Administrator, auth.user.id)
        if admin is None:
            raise IdentityError("session.invalid")
        return StaffProfile(name=auth.user.name, email=admin.email, role=admin.role)

    @router.patch("/admin/me", operation_id="editStaffProfile")
    async def edit_staff_profile(data: ProfileEdit, db: DB, auth: Auth) -> StaffProfile:
        auth.user.name = data.name
        profile = await staff_profile(db, auth)
        await db.commit()
        return profile

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

    @app.get("/internal/v1/orders/addresses/{address_id}", include_in_schema=False)
    async def checkout_address(
        address_id: UUID, version: Annotated[int, Query(ge=1)], request: Request, db: DB
    ) -> AddressResponse:
        scheme, _, token = request.headers.get("authorization", "").partition(" ")
        if scheme.lower() != "bearer" or not token or len(token) > 8192:
            raise IdentityError("service.unauthorized", 401)
        tokens: Tokens = request.app.state.sessions.tokens
        try:
            customer_id = tokens.address_snapshot_customer(token)
        except (jwt.InvalidTokenError, ValueError) as exc:
            raise IdentityError("service.unauthorized", 401) from exc
        address = await db.scalar(
            select(Address).where(Address.id == address_id, Address.user_id == customer_id)
        )
        if address is None:
            raise IdentityError("address.not_found", 404)
        if address.version != version:
            raise IdentityError("address.changed", 409)
        return AddressResponse.model_validate(address)

    async def checked_session(
        body: CatalogCheck, db: DB, kind: SessionKind, permission: str | None = None
    ) -> Authenticated:
        auth: Authenticated = await app.state.sessions.authenticate(db, body.access_token, kind)
        if permission is not None and permission not in auth.permissions:
            raise IdentityError("permission.denied", 403)
        if body.mutating:
            if body.origin not in settings.allowed_origins:
                raise IdentityError("origin.forbidden", 403)
            app.state.sessions.check_csrf(auth.session, body.csrf_token)
        return auth

    @app.post("/internal/v1/catalog/admin-check", include_in_schema=False)
    async def catalog_admin_check(body: CatalogCheck, request: Request, db: DB) -> CatalogPrincipal:
        authenticate_catalog(
            request.headers.get("authorization", ""), body, app.state.catalog_service_key
        )
        auth = await checked_session(body, db, "admin", "catalog.write")
        return CatalogPrincipal(
            user_id=auth.user.id, session_id=auth.session.id, permissions=auth.permissions
        )

    @app.post(CATALOG_MODERATOR_CHECK_PATH, include_in_schema=False)
    async def catalog_moderator_check(
        body: CatalogCheck, request: Request, db: DB
    ) -> CatalogPrincipal:
        authenticate_catalog_moderator(
            request.headers.get("authorization", ""), body, app.state.catalog_service_key
        )
        auth = await checked_session(body, db, "admin", "reviews.moderate")
        return CatalogPrincipal(
            user_id=auth.user.id, session_id=auth.session.id, permissions=auth.permissions
        )

    @app.post(CATALOG_CUSTOMER_CHECK_PATH, include_in_schema=False)
    async def catalog_customer_check(
        body: CatalogCheck, request: Request, db: DB
    ) -> CatalogCustomerPrincipal:
        authenticate_catalog_customer(
            request.headers.get("authorization", ""), body, app.state.catalog_service_key
        )
        auth = await checked_session(body, db, "customer")
        return CatalogCustomerPrincipal(user_id=auth.user.id)

    @app.post(SUPPORT_CHECK_PATH, include_in_schema=False)
    async def support_session_check(
        body: SupportCheck, request: Request, db: DB
    ) -> SupportPrincipal:
        authenticate_support(
            request.headers.get("authorization", ""), body, app.state.support_service_key
        )
        auth = await checked_session(
            body, db, body.kind, "support.reply" if body.kind == "admin" else None
        )
        can_manage = body.kind == "admin" and "users.manage" in auth.permissions
        if body.target_agent_id is not None:
            if (
                not body.mutating
                or body.kind != "admin"
                or (body.target_agent_id != auth.user.id and not can_manage)
            ):
                raise IdentityError("permission.denied", 403)
            target = await db.scalar(
                select(Administrator.user_id)
                .join(User, User.id == Administrator.user_id)
                .where(
                    Administrator.user_id == body.target_agent_id,
                    Administrator.role.in_(("support_agent", "super_admin")),
                    User.disabled.is_(False),
                )
            )
            if target is None:
                raise IdentityError("support.agent_unavailable", 403)
        return SupportPrincipal(user_id=auth.user.id, kind=body.kind, can_manage=can_manage)

    @app.post("/internal/v1/cart/customer-check", include_in_schema=False)
    async def cart_customer_check(body: CartCheck, request: Request, db: DB) -> CartPrincipal:
        authenticate_cart(
            request.headers.get("authorization", ""), body, app.state.cart_service_key
        )
        auth: Authenticated = await app.state.sessions.authenticate(
            db, body.access_token, "customer"
        )
        if body.mutating:
            if body.origin not in settings.allowed_origins:
                raise IdentityError("origin.forbidden", 403)
            app.state.sessions.check_csrf(auth.session, body.csrf_token)
        return CartPrincipal(user_id=auth.user.id, session_id=auth.session.id)

    management = APIRouter(prefix="/api/v1/admin/users", tags=["account management"])

    @management.get("", operation_id="listManagedAccounts")
    async def list_accounts(
        db: DB,
        _: AccountManager,
        kind: accounts.AccountKind | None = None,
        disabled: bool | None = None,
        before: UUID | None = None,
        limit: AccountPageSize = 25,
    ) -> accounts.AccountPage:
        return await accounts.list_accounts(db, kind, disabled, before, limit)

    @management.get("/audit", operation_id="listAccountAudit")
    async def list_account_audit(
        db: DB,
        _: AccountManager,
        target: UUID | None = None,
        before: UUID | None = None,
        limit: AccountPageSize = 25,
    ) -> accounts.AccountAuditPage:
        return await accounts.list_account_audit(db, target, before, limit)

    @management.get("/{user_id}", operation_id="getManagedAccount")
    async def get_account(db: DB, _: AccountManager, user_id: UUID) -> accounts.AccountSummary:
        user, admin = await accounts.target_account(db, user_id)
        return accounts.summary(user, admin.email if admin else None, admin.role if admin else None)

    @management.patch("/{user_id}/status", operation_id="setManagedAccountStatus")
    async def update_account_status(
        db: DB, actor: AccountManager, user_id: UUID, body: accounts.StatusChange
    ) -> accounts.AccountSummary:
        user, admin = await accounts.target_account(
            db, user_id, expected_version=body.expected_version
        )
        await accounts.change_status(db, user, admin, body.disabled, actor.user.id)
        await db.commit()
        return accounts.summary(user, admin.email if admin else None, admin.role if admin else None)

    @management.patch("/{user_id}/role", operation_id="setManagedStaffRole")
    async def update_staff_role(
        db: DB, actor: AccountManager, user_id: UUID, body: accounts.RoleChange
    ) -> accounts.AccountSummary:
        user, admin = await accounts.target_account(
            db, user_id, expected_version=body.expected_version
        )
        await accounts.change_role(db, user, admin, body.role, actor.user.id)
        await db.commit()
        return accounts.summary(user, admin.email if admin else None, admin.role if admin else None)

    app.include_router(router)
    app.include_router(management)
    app.include_router(service_tokens_router)
    app.add_middleware(BoundedBody, max_bytes=16384)
    return app


app = create_app()
