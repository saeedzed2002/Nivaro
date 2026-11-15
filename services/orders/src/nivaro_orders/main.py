import re
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from uuid import uuid4

import httpx
from fastapi import FastAPI, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from nivaro_orders.api.checkout import router
from nivaro_orders.api.limits import BoundedBody
from nivaro_orders.application.checkout_flow import CheckoutFlow
from nivaro_orders.domain.checkout import CheckoutError
from nivaro_orders.infrastructure.checkout_sources import CheckoutSources, SourceError
from nivaro_orders.infrastructure.database import Database
from nivaro_orders.infrastructure.http_json import UpstreamUnavailable
from nivaro_orders.infrastructure.reservations import CatalogReservations
from nivaro_orders.settings import Settings

SCHEMA = "0008_payment_initiations"


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        secret = settings.client_secret_file.read_text(encoding="utf-8").strip()
        if len(secret) < 32:
            raise ValueError("Orders service credential is missing or invalid")
        database = Database(settings)
        app.state.database = database
        try:
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(5, connect=2),
                trust_env=False,
                follow_redirects=False,
                limits=httpx.Limits(max_connections=20, max_keepalive_connections=10),
            ) as http:
                app.state.checkout = CheckoutFlow(
                    database,
                    settings,
                    CheckoutSources(http, settings, secret),
                    CatalogReservations(http, settings, secret),
                )
                yield
        finally:
            await database.engine.dispose()

    app = FastAPI(
        title="Nivaro Orders",
        version="0.2.0",
        lifespan=lifespan,
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )
    app.add_middleware(BoundedBody)

    @app.middleware("http")
    async def request_identity(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        candidate = request.headers.get("x-request-id", "")
        request.state.request_id = (
            candidate if re.fullmatch(r"[A-Za-z0-9_-]{1,64}", candidate) else str(uuid4())
        )
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Request-ID"] = request.state.request_id
        return response

    def error(request: Request, status: int, code: str) -> JSONResponse:
        return JSONResponse(
            {"error": {"code": code, "request_id": request.state.request_id}}, status_code=status
        )

    @app.exception_handler(CheckoutError)
    async def checkout_error(request: Request, exc: CheckoutError) -> JSONResponse:
        if isinstance(exc, SourceError):
            return error(request, exc.status, exc.code)
        status = {"checkout.not_found": 404, "checkout.invalid_idempotency_key": 422}.get(
            exc.code, 409
        )
        return error(request, status, exc.code)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
        return error(request, 422, "request.invalid")

    @app.exception_handler(SQLAlchemyError)
    @app.exception_handler(UpstreamUnavailable)
    async def unavailable(
        request: Request, exc: SQLAlchemyError | UpstreamUnavailable
    ) -> JSONResponse:
        return error(request, 503, "checkout.unavailable")

    @app.get("/health/live", include_in_schema=False)
    async def live() -> dict[str, str]:
        return {"service": "orders", "status": "ok"}

    @app.get("/health/ready", include_in_schema=False, response_model=None)
    async def ready() -> dict[str, str] | JSONResponse:
        database: Database = app.state.database
        try:
            async with database.sessions() as db:
                if await db.scalar(text("SELECT version_num FROM alembic_version")) == SCHEMA:
                    return {"service": "orders", "status": "ok", "schema": SCHEMA}
        except SQLAlchemyError:
            pass
        return JSONResponse({"service": "orders", "status": "unavailable"}, status_code=503)

    app.include_router(router)
    return app


app = create_app()
