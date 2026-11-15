import re
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from typing import Annotated
from uuid import UUID, uuid4

import httpx
from fastapi import APIRouter, Depends, FastAPI, Header, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from nivaro_payments import attempts
from nivaro_payments.authorization import OrdersAuthorization, require
from nivaro_payments.contracts import (
    AttemptView,
    OperationKey,
    PaymentError,
    PaymentIntent,
    RefundIntent,
    RefundView,
)
from nivaro_payments.limits import BoundedBody
from nivaro_payments.provider import Provider, Simulator
from nivaro_payments.settings import Database, Settings

SCHEMA = "0001_payment_attempts"
router = APIRouter(prefix="/internal/v1/payments", tags=["payments"])


async def session(request: Request) -> AsyncIterator[AsyncSession]:
    database: Database = request.app.state.database
    async with database.sessions() as db:
        yield db


def provider(request: Request) -> Provider:
    adapter: Provider = request.app.state.provider
    return adapter


DB = Annotated[AsyncSession, Depends(session)]
Adapter = Annotated[Provider, Depends(provider)]
Key = Annotated[OperationKey, Header(alias="Idempotency-Key")]


@router.post(
    "/attempts", response_model=AttemptView, dependencies=[Depends(require("payments.start"))]
)
async def start(body: PaymentIntent, key: Key, db: DB, adapter: Adapter) -> AttemptView:
    return AttemptView.model_validate(await attempts.start_payment(db, adapter, key, body))


@router.get(
    "/attempts/{attempt_id}",
    response_model=AttemptView,
    dependencies=[Depends(require("payments.read"))],
)
async def read(attempt_id: UUID, db: DB) -> AttemptView:
    return AttemptView.model_validate(await attempts.read_attempt(db, attempt_id))


@router.post(
    "/attempts/{attempt_id}/verify",
    response_model=AttemptView,
    dependencies=[Depends(require("payments.verify"))],
)
async def verify(attempt_id: UUID, db: DB, adapter: Adapter) -> AttemptView:
    return AttemptView.model_validate(await attempts.verify_payment(db, adapter, attempt_id))


@router.post(
    "/attempts/{attempt_id}/refunds",
    response_model=RefundView,
    dependencies=[Depends(require("payments.refund"))],
)
async def refund(
    attempt_id: UUID, body: RefundIntent, key: Key, db: DB, adapter: Adapter
) -> RefundView:
    return RefundView.model_validate(
        await attempts.refund_payment(db, adapter, attempt_id, key, body)
    )


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        database = Database(settings)
        app.state.database = database
        app.state.provider = Simulator()
        try:
            async with httpx.AsyncClient(
                base_url=str(settings.identity_url),
                follow_redirects=False,
                trust_env=False,
                timeout=httpx.Timeout(5, connect=2),
            ) as client:
                app.state.authorization = OrdersAuthorization(client, settings.identity_issuer)
                yield
        finally:
            await database.engine.dispose()

    app = FastAPI(
        title="Nivaro Payments",
        version="0.1.0",
        lifespan=lifespan,
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )
    app.add_middleware(BoundedBody)

    @app.middleware("http")
    async def correlation(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        candidate = request.headers.get("x-request-id", "")
        request.state.request_id = (
            candidate if re.fullmatch(r"[A-Za-z0-9_-]{1,64}", candidate) else str(uuid4())
        )
        result = await call_next(request)
        result.headers["Cache-Control"] = "no-store"
        result.headers["X-Request-ID"] = request.state.request_id
        return result

    def error(request: Request, code: str, status: int) -> JSONResponse:
        return JSONResponse(
            {"error": {"code": code, "request_id": request.state.request_id}}, status_code=status
        )

    @app.exception_handler(PaymentError)
    async def payment_error(request: Request, exc: PaymentError) -> JSONResponse:
        return error(request, exc.code, exc.status)

    @app.exception_handler(RequestValidationError)
    async def invalid(request: Request, exc: RequestValidationError) -> JSONResponse:
        return error(request, "request.invalid", 422)

    @app.exception_handler(SQLAlchemyError)
    async def unavailable(request: Request, exc: SQLAlchemyError) -> JSONResponse:
        return error(request, "payments.unavailable", 503)

    @app.get("/health/live", include_in_schema=False)
    async def live() -> dict[str, str]:
        return {"service": "payments", "status": "ok"}

    @app.get("/health/ready", include_in_schema=False, response_model=None)
    async def readiness(db: DB) -> dict[str, str] | JSONResponse:
        if await db.scalar(text("SELECT version_num FROM alembic_version")) == SCHEMA:
            return {"service": "payments", "status": "ok", "schema": SCHEMA}
        return JSONResponse({"service": "payments", "status": "unavailable"}, status_code=503)

    app.include_router(router)
    return app


app = create_app()
