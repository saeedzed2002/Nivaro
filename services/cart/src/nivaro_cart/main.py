from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from nivaro_cart.api.authorization import IdentityAuthorization
from nivaro_cart.api.builds import router as builds_router
from nivaro_cart.api.checkout import router as checkout_router
from nivaro_cart.api.comparison import router as comparison_router
from nivaro_cart.api.groups import router as groups_router
from nivaro_cart.api.items import router as items_router
from nivaro_cart.api.limits import BoundedBody
from nivaro_cart.api.merge import router as merge_router
from nivaro_cart.api.ownership import router
from nivaro_cart.api.transfers import router as transfers_router
from nivaro_cart.domain.errors import AuthorizationError, CartInputError, CommerceError
from nivaro_cart.domain.mutations import CartConflict, CartNotFound
from nivaro_cart.infrastructure.catalog import Catalog
from nivaro_cart.infrastructure.database import Database
from nivaro_cart.settings import Settings


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        database = Database(settings)
        app.state.database, app.state.settings = database, settings
        try:
            async with (
                httpx.AsyncClient(
                    base_url=settings.identity_url,
                    timeout=2,
                    trust_env=False,
                    limits=httpx.Limits(max_connections=8, max_keepalive_connections=4),
                ) as client,
                httpx.AsyncClient(
                    base_url=settings.catalog_url,
                    timeout=2,
                    trust_env=False,
                    limits=httpx.Limits(max_connections=8, max_keepalive_connections=4),
                ) as catalog_client,
            ):
                app.state.authorization = IdentityAuthorization(settings, client)
                app.state.catalog = Catalog(catalog_client)
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

    @app.exception_handler(RequestValidationError)
    async def invalid_request(request: Request, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(status_code=422, content={"error": {"code": "request.invalid"}})

    @app.exception_handler(SQLAlchemyError)
    async def database_error(request: Request, exc: SQLAlchemyError) -> JSONResponse:
        return JSONResponse(status_code=503, content={"error": {"code": "cart.unavailable"}})

    @app.exception_handler(CartConflict)
    async def conflict(request: Request, exc: CartConflict) -> JSONResponse:
        return JSONResponse(
            status_code=409,
            content={"error": {"code": exc.code, "current_version": exc.current_version}},
        )

    @app.exception_handler(CartNotFound)
    async def missing(request: Request, exc: CartNotFound) -> JSONResponse:
        return JSONResponse(status_code=404, content={"error": {"code": "cart.not_found"}})

    @app.exception_handler(CommerceError)
    async def commerce_error(request: Request, exc: CommerceError) -> JSONResponse:
        return JSONResponse(status_code=exc.status, content={"error": {"code": exc.code}})

    @app.exception_handler(CartInputError)
    async def input_error(request: Request, exc: CartInputError) -> JSONResponse:
        return JSONResponse(
            status_code=409 if str(exc) == "cart.limit" else 422,
            content={"error": {"code": str(exc)}},
        )

    @app.get("/health/live")
    async def live() -> dict[str, str]:
        return {"service": "cart", "status": "ok"}

    @app.get("/health/ready", response_model=None)
    async def ready() -> dict[str, str] | JSONResponse:
        try:
            async with app.state.database.sessions() as db:
                revision = await db.scalar(text("SELECT version_num FROM alembic_version"))
            if revision == "0007_paid_cleanup":
                return {"service": "cart", "status": "ok"}
        except SQLAlchemyError:
            pass
        return JSONResponse(status_code=503, content={"service": "cart", "status": "unavailable"})

    app.include_router(router)
    app.include_router(items_router)
    app.include_router(merge_router)
    app.include_router(builds_router)
    app.include_router(comparison_router)
    app.include_router(groups_router)
    app.include_router(transfers_router)
    app.include_router(checkout_router)
    app.add_middleware(BoundedBody)
    return app


app = create_app()
