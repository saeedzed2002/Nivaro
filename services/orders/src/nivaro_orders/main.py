from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from nivaro_orders.infrastructure.database import Database
from nivaro_orders.settings import Settings

SCHEMA = "0001_orders"


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        database = Database(settings)
        app.state.database = database
        try:
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

    return app


app = create_app()
