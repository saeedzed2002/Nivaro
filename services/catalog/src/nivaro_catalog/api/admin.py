"""Staff catalog reads. Mutations will use the same fresh authorization dependency."""

from collections.abc import AsyncIterator
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from nivaro_catalog.api.authorization import CatalogAdmin
from nivaro_catalog.api.schemas import ErrorEnvelope
from nivaro_catalog.domain.contracts import Localized, Variant
from nivaro_catalog.domain.search import search_terms
from nivaro_catalog.infrastructure.models import ProductRow, VariantRow
from nivaro_catalog.infrastructure.repository import variant_contract

Status = Literal["draft", "published", "archived"]


class AdminProduct(BaseModel):
    id: UUID
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


class AdminProductDetail(AdminProduct):
    description: Localized
    highlights: list[str]
    variants: list[Variant]


async def database(request: Request) -> AsyncIterator[AsyncSession]:
    async for session in request.app.state.database.session():
        yield session


DB = Annotated[AsyncSession, Depends(database)]
router = APIRouter(
    prefix="/api/v1/admin/catalog",
    tags=["catalog-administration"],
    responses={code: {"model": ErrorEnvelope} for code in (401, 403, 404, 422, 503)},
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
    product = await db.scalar(
        select(ProductRow)
        .where(ProductRow.id == product_id)
        .options(selectinload(ProductRow.variants).selectinload(VariantRow.offers))
    )
    if product is None:
        raise HTTPException(404, "Product not found")
    return AdminProductDetail(
        **summary(product, len(product.variants)).model_dump(),
        description=Localized.model_validate(product.description),
        highlights=product.highlights,
        variants=[variant_contract(v) for v in sorted(product.variants, key=lambda item: item.sku)],
    )
