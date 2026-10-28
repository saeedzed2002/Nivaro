"""Staff catalog operations; every route resolves fresh administrator authorization."""

from collections.abc import AsyncIterator
from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, JsonValue
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from nivaro_catalog.api.authorization import CatalogAdmin
from nivaro_catalog.api.schemas import ErrorEnvelope
from nivaro_catalog.application.administration import read_product, transaction
from nivaro_catalog.domain.administration import (
    OfferChange,
    ProductContent,
    ProductEdit,
    StatusChange,
    StockChange,
    VariantContent,
)
from nivaro_catalog.domain.contracts import Localized, Variant
from nivaro_catalog.domain.search import search_terms
from nivaro_catalog.infrastructure.models import AuditRow, ProductRow, VariantRow
from nivaro_catalog.infrastructure.repository import variant_contract

Status = Literal["draft", "published", "archived"]


class AdminProduct(BaseModel):
    id: UUID
    version: int
    slug: str
    name: str
    category_id: UUID
    brand: str
    status: Status
    image: str
    image_ready: bool
    image_kind: str
    variant_count: int


class AdminProductPage(BaseModel):
    items: list[AdminProduct]
    total: int
    page: int
    page_size: int


class AdminVariant(Variant):
    version: int


class AdminProductDetail(AdminProduct):
    description: Localized
    highlights: list[str]
    variants: list[AdminVariant]


class AuditEntry(BaseModel):
    id: UUID
    actor_id: UUID
    action: str
    target_id: UUID
    before: dict[str, JsonValue]
    after: dict[str, JsonValue]
    reason: str
    request_id: str
    created_at: datetime


class AuditPage(BaseModel):
    items: list[AuditEntry]
    total: int
    page: int
    page_size: int


async def database(request: Request) -> AsyncIterator[AsyncSession]:
    async for session in request.app.state.database.session():
        yield session


DB = Annotated[AsyncSession, Depends(database)]
router = APIRouter(
    prefix="/api/v1/admin/catalog",
    tags=["catalog-administration"],
    responses={code: {"model": ErrorEnvelope} for code in (401, 403, 404, 409, 422, 503)},
)


def summary(product: ProductRow, count: int) -> AdminProduct:
    return AdminProduct.model_validate(
        {
            **{
                field: getattr(product, field)
                for field in AdminProduct.model_fields
                if field != "variant_count"
            },
            "variant_count": count,
        }
    )


@router.get("/products", operation_id="listAdminProducts")
async def products(
    auth: CatalogAdmin,
    db: DB,
    q: Annotated[str, Query(max_length=100)] = "",
    status: Status | None = None,
    category_id: UUID | None = None,
    page: Annotated[int, Query(ge=1, le=10000)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 24,
) -> AdminProductPage:
    statement = select(ProductRow)
    if status:
        statement = statement.where(ProductRow.status == status)
    if category_id:
        statement = statement.where(ProductRow.category_id == category_id)
    terms = search_terms(q)
    if terms:
        # SKU search is exact/case-insensitive; names use the existing normalized index.
        statement = statement.where(
            ProductRow.search_tokens.contains(terms)
            | ProductRow.variants.any(func.lower(VariantRow.sku) == q.strip().lower())
        )
    total = await db.scalar(select(func.count()).select_from(statement.subquery())) or 0
    counts = (
        select(func.count(VariantRow.id))
        .where(VariantRow.product_id == ProductRow.id)
        .correlate(ProductRow)
        .scalar_subquery()
    )
    rows = await db.execute(
        statement.add_columns(counts)
        .order_by(ProductRow.updated_at.desc(), ProductRow.id)
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    return AdminProductPage(
        items=[summary(product, count) for product, count in rows],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/products/{product_id}", operation_id="getAdminProduct")
async def detail(product_id: UUID, auth: CatalogAdmin, db: DB) -> AdminProductDetail:
    return await product_detail(db, product_id)


async def product_detail(db: AsyncSession, product_id: UUID) -> AdminProductDetail:
    product = await read_product(db, product_id)
    return AdminProductDetail(
        **summary(product, len(product.variants)).model_dump(),
        description=Localized.model_validate(product.description),
        highlights=product.highlights,
        variants=[
            AdminVariant(**variant_contract(v).model_dump(), version=v.version)
            for v in sorted(product.variants, key=lambda item: item.sku)
        ],
    )


@router.post("/products", operation_id="createAdminProduct", status_code=201)
async def create(
    body: ProductContent, auth: CatalogAdmin, db: DB, request: Request
) -> AdminProductDetail:
    async with transaction(db, auth.user_id, request.state.request_id) as service:
        product_id = await service.create(body)
        result = await product_detail(db, product_id)
    return result


@router.put("/products/{product_id}", operation_id="updateAdminProduct")
async def edit(
    product_id: UUID, body: ProductEdit, auth: CatalogAdmin, db: DB, request: Request
) -> AdminProductDetail:
    async with transaction(db, auth.user_id, request.state.request_id) as service:
        await service.edit(product_id, body)
        result = await product_detail(db, product_id)
    return result


@router.put("/products/{product_id}/status", operation_id="setAdminProductStatus")
async def status(
    product_id: UUID, body: StatusChange, auth: CatalogAdmin, db: DB, request: Request
) -> AdminProductDetail:
    async with transaction(db, auth.user_id, request.state.request_id) as service:
        await service.status(product_id, body)
        result = await product_detail(db, product_id)
    return result


@router.post("/products/{product_id}/variants", operation_id="createAdminVariant", status_code=201)
async def create_variant(
    product_id: UUID, body: VariantContent, auth: CatalogAdmin, db: DB, request: Request
) -> AdminProductDetail:
    async with transaction(db, auth.user_id, request.state.request_id) as service:
        await service.create_variant(product_id, body)
        result = await product_detail(db, product_id)
    return result


@router.put("/products/{product_id}/variants/{variant_id}", operation_id="updateAdminVariant")
async def edit_variant(
    product_id: UUID,
    variant_id: UUID,
    body: VariantContent,
    auth: CatalogAdmin,
    db: DB,
    request: Request,
) -> AdminProductDetail:
    async with transaction(db, auth.user_id, request.state.request_id) as service:
        await service.edit_variant(product_id, variant_id, body)
        result = await product_detail(db, product_id)
    return result


@router.put("/products/{product_id}/variants/{variant_id}/stock", operation_id="setAdminStock")
async def stock(
    product_id: UUID,
    variant_id: UUID,
    body: StockChange,
    auth: CatalogAdmin,
    db: DB,
    request: Request,
) -> AdminProductDetail:
    async with transaction(db, auth.user_id, request.state.request_id) as service:
        await service.stock(product_id, variant_id, body)
        result = await product_detail(db, product_id)
    return result


@router.put("/products/{product_id}/variants/{variant_id}/offers", operation_id="setAdminOffer")
async def offer(
    product_id: UUID,
    variant_id: UUID,
    body: OfferChange,
    auth: CatalogAdmin,
    db: DB,
    request: Request,
) -> AdminProductDetail:
    async with transaction(db, auth.user_id, request.state.request_id) as service:
        await service.offer(product_id, variant_id, body)
        result = await product_detail(db, product_id)
    return result


@router.get("/products/{product_id}/audit", operation_id="listAdminProductAudit")
async def audit(
    product_id: UUID,
    auth: CatalogAdmin,
    db: DB,
    page: Annotated[int, Query(ge=1, le=10000)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 24,
) -> AuditPage:
    if await db.get(ProductRow, product_id) is None:
        raise HTTPException(404, "Product not found")
    query = select(AuditRow).where(AuditRow.product_id == product_id)
    total = await db.scalar(select(func.count()).select_from(query.subquery())) or 0
    rows = await db.scalars(
        query.order_by(AuditRow.created_at.desc(), AuditRow.id)
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    return AuditPage(
        items=[AuditEntry.model_validate(row, from_attributes=True) for row in rows],
        total=total,
        page=page,
        page_size=page_size,
    )
