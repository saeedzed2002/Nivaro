from typing import Literal
from uuid import UUID

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload, selectinload

from nivaro_catalog.api.schemas import (
    Comparison,
    ComparisonColumn,
    ComparisonRequest,
    ComparisonRow,
    ProductPage,
)
from nivaro_catalog.domain.contracts import Category, Localized, Market, Product, Variant
from nivaro_catalog.domain.search import search_terms
from nivaro_catalog.infrastructure.models import CategoryRow, OfferRow, ProductRow, VariantRow

Sort = Literal["featured", "name", "newest", "price_asc", "price_desc"]


def public_products() -> Select[tuple[ProductRow]]:
    return (
        select(ProductRow)
        .where(
            ProductRow.status == "published",
            ProductRow.image_ready.is_(True),
            ProductRow.variants.any(),
        )
        .options(
            joinedload(ProductRow.category),
            selectinload(ProductRow.variants).selectinload(VariantRow.offers),
        )
    )


def variant_contract(row: VariantRow) -> Variant:
    return Variant.model_validate(
        {
            "id": row.id,
            "sku": row.sku,
            "packaging": row.packaging,
            "specifications": row.specifications,
            "spec_version": row.spec_version,
            "evidence": row.evidence,
            "stock_kind": row.stock_kind,
            "on_hand": row.on_hand,
            "reserved": row.reserved,
            "stock_verified": row.stock_verified,
            "offers": [
                {
                    "market": o.market,
                    "currency": o.currency,
                    "amount_minor": o.amount_minor,
                    "price_version": o.price_version,
                    "available_for_sale": o.available_for_sale,
                    "reference_only": o.reference_only,
                    "source": o.source,
                    "seller": o.seller,
                }
                for o in sorted(row.offers, key=lambda o: o.market)
            ],
        }
    )


def product_contract(row: ProductRow) -> Product:
    return Product.model_validate(
        {
            "id": row.id,
            "slug": row.slug,
            "name": row.name,
            "description": row.description,
            "category": row.category.slug,
            "brand": row.brand,
            "image": row.image,
            "image_kind": row.image_kind,
            "highlights": row.highlights,
            "variants": [variant_contract(v) for v in sorted(row.variants, key=lambda v: v.sku)],
        }
    )


async def categories(session: AsyncSession) -> list[Category]:
    rows = await session.scalars(select(CategoryRow).order_by(CategoryRow.slug))
    return [
        Category(
            id=r.id,
            slug=r.slug,
            name=Localized.model_validate(r.name),
            image=r.image,
            parent_id=r.parent_id,
        )
        for r in rows
    ]


async def products(
    session: AsyncSession,
    *,
    q: str = "",
    category: str = "",
    brand: str = "",
    market: Market = "ir",
    sort: Sort = "featured",
    page: int = 1,
    page_size: int = 24,
    min_price: int | None = None,
    max_price: int | None = None,
    in_stock: bool = False,
) -> ProductPage:
    stmt = public_products()
    terms = search_terms(q)
    if terms:
        stmt = stmt.where(ProductRow.search_tokens.contains(terms))
    if category:
        stmt = stmt.where(ProductRow.category.has(CategoryRow.slug == category))
    if brand:
        stmt = stmt.where(ProductRow.brand == brand)
    price = (
        select(func.min(OfferRow.amount_minor))
        .join(VariantRow)
        .where(VariantRow.product_id == ProductRow.id, OfferRow.market == market)
        .correlate(ProductRow)
        .scalar_subquery()
    )
    if min_price is not None:
        stmt = stmt.where(price >= min_price)
    if max_price is not None:
        stmt = stmt.where(price <= max_price)
    if in_stock:
        stmt = stmt.where(
            ProductRow.variants.any(
                (VariantRow.stock_verified.is_(True))
                & (VariantRow.on_hand > VariantRow.reserved)
                & VariantRow.offers.any(
                    (OfferRow.market == market) & OfferRow.available_for_sale.is_(True)
                )
            )
        )
    count = await session.scalar(select(func.count()).select_from(stmt.subquery()))
    order = {
        "featured": ProductRow.created_at,
        "newest": ProductRow.created_at.desc(),
        "name": ProductRow.name,
        "price_asc": price.asc().nulls_last(),
        "price_desc": price.desc().nulls_last(),
    }[sort]
    rows = await session.scalars(
        stmt.order_by(order, ProductRow.id).offset((page - 1) * page_size).limit(page_size)
    )
    return ProductPage(
        items=[product_contract(r) for r in rows], page=page, page_size=page_size, total=count or 0
    )


async def product(session: AsyncSession, slug: str) -> Product | None:
    row = await session.scalar(public_products().where(ProductRow.slug == slug))
    return product_contract(row) if row else None


async def selected_products(session: AsyncSession, ids: list[UUID]) -> list[Product]:
    if not ids:
        return []
    rows = await session.scalars(
        public_products().where(ProductRow.variants.any(VariantRow.id.in_(ids)))
    )
    return [product_contract(r) for r in rows]


def compare(request: ComparisonRequest, selected: list[Product]) -> Comparison:
    lookup = {v.id: (p, v) for p in selected for v in p.variants}
    if any(identifier not in lookup for identifier in request.variant_ids):
        raise ValueError("Selected variant is unavailable")
    pairs = [lookup[identifier] for identifier in request.variant_ids]
    if len({p.category for p, _ in pairs}) != 1:
        raise ValueError("Comparison requires two products in the same category")
    columns = [
        ComparisonColumn(
            product_id=p.id,
            slug=p.slug,
            name=p.name,
            variant=v,
            offer=next((o for o in v.offers if o.market == request.market), None),
        )
        for p, v in pairs
    ]
    facts = [v.specifications.model_dump() for _, v in pairs]
    rows = []
    for key in sorted(set(facts[0]) | set(facts[1])):
        if key == "kind":
            continue
        # Scalar specification values already use normalized units in their field names.
        # Nested fit lists are retained on the variant but not flattened into fake numbers.
        values = [f.get(key) for f in facts]
        if any(isinstance(value, (dict, list)) for value in values):
            continue
        rows.append(ComparisonRow(key=key, values=values, different=values[0] != values[1]))
    return Comparison(
        market=request.market,
        currency=request.currency,
        category=pairs[0][0].category,
        columns=columns,
        rows=rows,
    )
