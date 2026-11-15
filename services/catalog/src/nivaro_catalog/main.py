import re
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from typing import Annotated
from uuid import UUID, uuid4

import httpx
from fastapi import APIRouter, Depends, FastAPI, HTTPException, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import ValidationError
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.responses import Response

from nivaro_catalog.api.admin import router as admin_router
from nivaro_catalog.api.authorization import AuthorizationError, IdentityAuthorization
from nivaro_catalog.api.categories import router as categories_router
from nivaro_catalog.api.checkout import router as checkout_router
from nivaro_catalog.api.limits import BoundedBody
from nivaro_catalog.api.media import router as media_router
from nivaro_catalog.api.schemas import (
    Comparison,
    ComparisonRequest,
    ErrorDetail,
    ErrorEnvelope,
    ProductPage,
    SummaryRequest,
    SummaryResponse,
)
from nivaro_catalog.domain.administration import AdministrationError
from nivaro_catalog.domain.checkout import CheckoutError
from nivaro_catalog.domain.contracts import (
    Category,
    Evaluation,
    EvaluationRequest,
    Market,
    Product,
    Variant,
)
from nivaro_catalog.domain.evaluation import SelectionError, evaluate
from nivaro_catalog.infrastructure import repository
from nivaro_catalog.infrastructure.database import Database
from nivaro_catalog.infrastructure.public_cache import PublicCache
from nivaro_catalog.settings import Settings


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = Settings()
    database = Database(settings)
    app.state.database = database
    cache = PublicCache(settings)
    app.state.public_cache = cache
    async with httpx.AsyncClient(
        base_url=settings.identity_url,
        timeout=httpx.Timeout(2, pool=1),
        limits=httpx.Limits(max_connections=20, max_keepalive_connections=10),
        trust_env=False,
        follow_redirects=False,
    ) as client:
        app.state.authorization = IdentityAuthorization(settings, client)
        try:
            yield
        finally:
            await cache.close()
            await database.engine.dispose()


app = FastAPI(
    title="Nivaro Catalog",
    version="0.2.0",
    lifespan=lifespan,
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)


def error(
    request: Request, status: int, code: str, message: str, details: list[str] | None = None
) -> JSONResponse:
    envelope = ErrorEnvelope(
        error=ErrorDetail(
            code=code,
            message=message,
            details=details or [],
            request_id=getattr(request.state, "request_id", "unassigned"),
        )
    )
    return JSONResponse(
        status_code=status, content=envelope.model_dump(), headers={"Cache-Control": "no-store"}
    )


@app.middleware("http")
async def request_identity(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    candidate = request.headers.get("x-request-id", "")
    request.state.request_id = (
        candidate if re.fullmatch(r"[A-Za-z0-9_-]{1,64}", candidate) else str(uuid4())
    )
    response = await call_next(request)
    response.headers["X-Request-ID"] = request.state.request_id
    response.headers["Cache-Control"] = "no-store"
    return response


@app.exception_handler(RequestValidationError)
async def validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
    # Avoid returning input/context which can contain secrets or arbitrarily large strings.
    return error(
        request,
        422,
        "request.invalid",
        "Invalid catalog request",
        [".".join(str(v) for v in e["loc"]) for e in exc.errors()[:20]],
    )


@app.exception_handler(StarletteHTTPException)
async def http_error(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    return error(
        request,
        exc.status_code,
        "catalog.not_found"
        if exc.status_code == 404
        else "catalog.unavailable"
        if exc.status_code == 503
        else "request.invalid",
        str(exc.detail),
    )


@app.exception_handler(SQLAlchemyError)
async def database_error(request: Request, exc: SQLAlchemyError) -> JSONResponse:
    return error(request, 503, "catalog.unavailable", "Catalog is temporarily unavailable")


@app.exception_handler(AuthorizationError)
async def authorization_error(request: Request, exc: AuthorizationError) -> JSONResponse:
    message = (
        "Service authorization could not be established"
        if request.url.path.startswith("/internal/")
        else "Administrator authorization could not be established"
    )
    return error(request, exc.status, exc.code, message)


@app.exception_handler(ValidationError)
async def invalid_catalog_data(request: Request, exc: ValidationError) -> JSONResponse:
    # Invalid stored facts fail closed; never return raw data or guess replacement values.
    return error(request, 503, "catalog.invalid_data", "Catalog data requires correction")


@app.exception_handler(AdministrationError)
async def administration_error(request: Request, exc: AdministrationError) -> JSONResponse:
    return error(request, exc.status, exc.code, exc.message)


@app.exception_handler(CheckoutError)
async def checkout_error(request: Request, exc: CheckoutError) -> JSONResponse:
    return error(request, exc.status, exc.code, exc.message, exc.details)


async def session(request: Request) -> AsyncIterator[AsyncSession]:
    async for connection in request.app.state.database.session():
        yield connection


SessionDep = Annotated[AsyncSession, Depends(session)]
router = APIRouter(
    prefix="/api/v1/catalog",
    tags=["catalog"],
    responses={
        404: {"model": ErrorEnvelope},
        422: {"model": ErrorEnvelope},
        503: {"model": ErrorEnvelope},
    },
)


@app.get("/health/live", include_in_schema=False)
async def live() -> dict[str, str]:
    return {"status": "ok", "service": "catalog"}


@app.get("/health/ready", include_in_schema=False)
async def ready(db: SessionDep) -> dict[str, str]:
    revision = await db.scalar(text("SELECT version_num FROM alembic_version"))
    if revision != "0009_paid_reservation":
        raise HTTPException(503, "Catalog schema revision is not ready")
    return {"status": "ok", "service": "catalog", "schema": revision}


@router.get("/categories", operation_id="listCategories")
async def categories(db: SessionDep) -> list[Category]:
    return await repository.categories(db)


@router.get("/products", operation_id="listProducts")
async def products(
    request: Request,
    db: SessionDep,
    q: Annotated[str, Query(max_length=100)] = "",
    category: Annotated[str, Query(max_length=80)] = "",
    brand: Annotated[str, Query(max_length=120)] = "",
    market: Market = "ir",
    sort: repository.Sort = "featured",
    page: Annotated[int, Query(ge=1, le=10000)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 24,
    min_price: Annotated[int | None, Query(ge=0, le=9_000_000_000_000)] = None,
    max_price: Annotated[int | None, Query(ge=0, le=9_000_000_000_000)] = None,
    in_stock: bool = False,
) -> ProductPage:
    if min_price is not None and max_price is not None and min_price > max_price:
        raise HTTPException(422, "Minimum price exceeds maximum price")

    async def load() -> ProductPage:
        return await repository.products(
            db,
            q=q,
            category=category,
            brand=brand,
            market=market,
            sort=sort,
            page=page,
            page_size=page_size,
            min_price=min_price,
            max_price=max_price,
            in_stock=in_stock,
        )

    cache: PublicCache = request.app.state.public_cache
    return await cache.read(
        db,
        ProductPage,
        (q, category, brand, market, sort, page, page_size, min_price, max_price, in_stock),
        load,
    )


@router.get("/products/{slug}", operation_id="getProduct")
async def product(slug: str, db: SessionDep, request: Request) -> Product:
    async def load() -> Product:
        result = await repository.product(db, slug)
        if result is None:
            raise HTTPException(404, "Product not found")
        return result

    cache: PublicCache = request.app.state.public_cache
    return await cache.read(db, Product, (slug,), load)


@router.post("/comparisons", operation_id="compareProducts")
async def comparison(body: ComparisonRequest, db: SessionDep) -> Comparison:
    selected = await repository.selected_products(db, body.variant_ids)
    try:
        return repository.compare(body, selected)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.post("/build-evaluations", operation_id="evaluateBuild")
async def build_evaluation(body: EvaluationRequest, db: SessionDep) -> Evaluation:
    selected = await repository.selected_products(db, [s.variant_id for s in body.selections])
    variants = {v.id: v for p in selected for v in p.variants}
    try:
        return evaluate(body, variants)
    except SelectionError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.get("/variants/{variant_id}", operation_id="getVariant")
async def variant(variant_id: UUID, db: SessionDep) -> Variant:
    selected = await repository.selected_products(db, [variant_id])
    for product in selected:
        for item in product.variants:
            if item.id == variant_id:
                return item
    raise HTTPException(404, "Variant not found")


@router.post("/variant-summaries", operation_id="getVariantSummaries")
async def variant_summaries(body: SummaryRequest, db: SessionDep) -> SummaryResponse:
    # Authoritative read: never use the public listing/detail cache for carts.
    return await repository.variant_summaries(db, body)


app.include_router(router)
app.include_router(admin_router)
app.include_router(categories_router)
app.include_router(media_router)
app.include_router(checkout_router)
app.add_middleware(BoundedBody)
