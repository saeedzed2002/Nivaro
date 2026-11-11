from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from nivaro_cart.api.authorization import IdentityAuthorization
from nivaro_cart.api.ownership import router
from nivaro_cart.domain.errors import AuthorizationError
from nivaro_cart.infrastructure.database import Database
from nivaro_cart.settings import Settings


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        database = Database(settings)
        app.state.database, app.state.settings = database, settings
        try:
            async with httpx.AsyncClient(
                base_url=settings.identity_url,
                timeout=2,
                trust_env=False,
                limits=httpx.Limits(max_connections=8, max_keepalive_connections=4),
            ) as client:
                app.state.authorization = IdentityAuthorization(settings, client)
                yield
        finally:
            await database.engine.dispose()

    app = FastAPI(
        title="Nivaro Cart",
        version="0.2.0",
        lifespan=lifespan,
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )

    @app.middleware("http")
    async def private_responses(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response

    @app.exception_handler(AuthorizationError)
    async def authorization_error(request: Request, exc: AuthorizationError) -> JSONResponse:
        return JSONResponse(status_code=exc.status, content={"error": {"code": exc.code}})

    @app.exception_handler(SQLAlchemyError)
    async def database_error(request: Request, exc: SQLAlchemyError) -> JSONResponse:
        return JSONResponse(status_code=503, content={"error": {"code": "cart.unavailable"}})

    @app.get("/health/live")
    async def live() -> dict[str, str]:
        return {"service": "cart", "status": "ok"}

    @app.get("/health/ready", response_model=None)
    async def ready() -> dict[str, str] | JSONResponse:
        try:
            async with app.state.database.sessions() as db:
                revision = await db.scalar(text("SELECT version_num FROM alembic_version"))
            if revision == "0002_guest_csrf":
                return {"service": "cart", "status": "ok"}
        except SQLAlchemyError:
            pass
        return JSONResponse(status_code=503, content={"service": "cart", "status": "unavailable"})

    app.include_router(router)
    return app


app = create_app()
