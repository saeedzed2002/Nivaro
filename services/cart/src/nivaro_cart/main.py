from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from nivaro_cart.infrastructure.database import Database
from nivaro_cart.settings import Settings


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    database = Database(Settings())
    app.state.database = database
    try:
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


@app.get("/health/live")
async def live() -> dict[str, str]:
    return {"service": "cart", "status": "ok"}


@app.get("/health/ready", response_model=None)
async def ready() -> dict[str, str] | JSONResponse:
    try:
        async with app.state.database.sessions() as db:
            revision = await db.scalar(text("SELECT version_num FROM alembic_version"))
        if revision == "0001_cart":
            return {"service": "cart", "status": "ok"}
    except SQLAlchemyError:
        pass
    return JSONResponse(status_code=503, content={"service": "cart", "status": "unavailable"})
