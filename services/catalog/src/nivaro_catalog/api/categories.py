"""Freshly authorized, versioned category administration; no destructive delete route."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query, Request
from sqlalchemy import Select, func, select

from nivaro_catalog.api.admin import DB, AuditEntry, AuditPage
from nivaro_catalog.api.authorization import CatalogAdmin
from nivaro_catalog.api.schemas import ErrorEnvelope
from nivaro_catalog.application.administration import transaction
from nivaro_catalog.application.categories import save_category
from nivaro_catalog.domain.administration import AdministrationError, CategoryContent, CategoryEdit
from nivaro_catalog.domain.contracts import Category, Localized
from nivaro_catalog.infrastructure.models import CategoryAuditRow, CategoryRow, ProductRow


class AdminCategory(Category):
    version: int
    product_count: int
    child_count: int


router = APIRouter(
    prefix="/api/v1/admin/catalog/categories",
    tags=["catalog-administration"],
    responses={code: {"model": ErrorEnvelope} for code in (401, 403, 404, 409, 422, 503)},
)


def category_query() -> Select[CategoryRow, int, int]:
    products = (
        select(func.count())
        .where(ProductRow.category_id == CategoryRow.id)
        .correlate(CategoryRow)
        .scalar_subquery()
    )
    children = CategoryRow.__table__.alias("child")
    child_count = (
        select(func.count())
        .where(children.c.parent_id == CategoryRow.id)
        .correlate(CategoryRow)
        .scalar_subquery()
    )
    return select(CategoryRow, products.label("product_count"), child_count.label("child_count"))


async def detail(db: DB, category_id: UUID) -> AdminCategory:
    result = (await db.execute(category_query().where(CategoryRow.id == category_id))).one_or_none()
    if result is None:
        raise AdministrationError("catalog.category_not_found", "Category not found", 404)
    row, products, children = result
    return AdminCategory(
        id=row.id,
        slug=row.slug,
        name=Localized.model_validate(row.name),
        image=row.image,
        parent_id=row.parent_id,
        version=row.version,
        product_count=products,
        child_count=children,
    )


@router.get("", operation_id="listAdminCategories")
async def categories(auth: CatalogAdmin, db: DB) -> list[AdminCategory]:
    rows = (await db.execute(category_query().order_by(CategoryRow.slug).limit(1000))).all()
    return [
        AdminCategory(
            id=row.id,
            slug=row.slug,
            name=Localized.model_validate(row.name),
            image=row.image,
            parent_id=row.parent_id,
            version=row.version,
            product_count=products,
            child_count=children,
        )
        for row, products, children in rows
    ]


@router.post("", operation_id="createAdminCategory", status_code=201)
async def create(
    body: CategoryContent, auth: CatalogAdmin, db: DB, request: Request
) -> AdminCategory:
    async with transaction(db, auth.user_id, request.state.request_id) as service:
        category_id = await save_category(service, body)
        result = await detail(db, category_id)
    return result


@router.put("/{category_id}", operation_id="updateAdminCategory")
async def edit(
    category_id: UUID, body: CategoryEdit, auth: CatalogAdmin, db: DB, request: Request
) -> AdminCategory:
    async with transaction(db, auth.user_id, request.state.request_id) as service:
        await save_category(service, body, category_id)
        result = await detail(db, category_id)
    return result


@router.get("/{category_id}/audit", operation_id="listAdminCategoryAudit")
async def audit(
    category_id: UUID,
    auth: CatalogAdmin,
    db: DB,
    page: Annotated[int, Query(ge=1, le=10000)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 24,
) -> AuditPage:
    await detail(db, category_id)
    query = select(CategoryAuditRow).where(CategoryAuditRow.category_id == category_id)
    total = await db.scalar(select(func.count()).select_from(query.subquery())) or 0
    rows = await db.scalars(
        query.order_by(CategoryAuditRow.created_at.desc(), CategoryAuditRow.id)
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    return AuditPage(
        items=[AuditEntry.model_validate(row, from_attributes=True) for row in rows],
        total=total,
        page=page,
        page_size=page_size,
    )
