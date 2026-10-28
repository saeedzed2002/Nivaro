"""Short catalog-owned transactions. All staff writes lock product, then variant/offer.

No identity/network calls run while database locks are held. The API resolves fresh
authorization first. Future stock reservation writers must lock variants in ID order
and advance variant.version; they must not acquire a product lock after a variant.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from nivaro_catalog.domain.administration import (
    AdministrationError,
    OfferChange,
    ProductContent,
    ProductEdit,
    StatusChange,
    StockChange,
    VariantContent,
)
from nivaro_catalog.domain.search import search_index
from nivaro_catalog.infrastructure.models import (
    AuditRow,
    CategoryRow,
    OfferRow,
    ProductRow,
    VariantRow,
)
from nivaro_catalog.infrastructure.repository import variant_contract

CONTENT_FIELDS = ("slug", "name", "description", "category_id", "brand", "highlights")
VARIANT_FIELDS = ("sku", "packaging", "specifications", "evidence", "spec_version", "version")
OFFER_FIELDS = (
    "market",
    "currency",
    "amount_minor",
    "price_version",
    "available_for_sale",
    "reference_only",
    "source",
    "seller",
)


def snapshot(row: Any, fields: tuple[str, ...]) -> dict[str, Any]:
    return {
        field: str(value) if isinstance(value := getattr(row, field), UUID) else value
        for field in fields
    }


async def read_product(db: AsyncSession, product_id: UUID) -> ProductRow:
    product = await db.scalar(
        select(ProductRow)
        .where(ProductRow.id == product_id)
        .options(selectinload(ProductRow.variants).selectinload(VariantRow.offers))
        .execution_options(populate_existing=True)
    )
    if product is None:
        raise AdministrationError("catalog.not_found", "Product not found", 404)
    return product


class Administration:
    def __init__(self, db: AsyncSession, actor_id: UUID, request_id: str) -> None:
        self.db, self.actor_id, self.request_id = db, actor_id, request_id

    def audit(
        self,
        product_id: UUID,
        action: str,
        target_id: UUID,
        before: dict[str, Any],
        after: dict[str, Any],
        reason: str = "",
    ) -> None:
        self.db.add(
            AuditRow(
                id=uuid4(),
                product_id=product_id,
                actor_id=self.actor_id,
                action=action,
                target_id=target_id,
                before=before,
                after=after,
                reason=reason,
                request_id=self.request_id,
            )
        )

    async def product(self, product_id: UUID, expected_version: int) -> ProductRow:
        row = await self.db.scalar(
            select(ProductRow).where(ProductRow.id == product_id).with_for_update()
        )
        if row is None:
            raise AdministrationError("catalog.not_found", "Product not found", 404)
        if row.version != expected_version:
            raise AdministrationError(
                "catalog.version_conflict", "Reload the current product before editing"
            )
        return row

    async def variant(self, product_id: UUID, variant_id: UUID) -> VariantRow:
        row = await self.db.scalar(
            select(VariantRow)
            .where(VariantRow.id == variant_id, VariantRow.product_id == product_id)
            .with_for_update()
        )
        if row is None:
            raise AdministrationError("catalog.not_found", "Variant not found in this product", 404)
        return row

    async def category_exists(self, category_id: UUID) -> None:
        if await self.db.get(CategoryRow, category_id) is None:
            raise AdministrationError(
                "catalog.category_not_found", "Select an existing category", 422
            )

    async def reindex(self, product: ProductRow) -> None:
        skus = await self.db.scalars(
            select(VariantRow.sku).where(VariantRow.product_id == product.id)
        )
        product.search_tokens = search_index(
            " ".join(
                [
                    product.name,
                    product.brand,
                    *product.description.values(),
                    *skus,
                ]
            )
        )

    async def create(self, command: ProductContent) -> UUID:
        await self.category_exists(command.category_id)
        product = ProductRow(
            id=uuid4(),
            **command.model_dump(exclude={"description"}),
            description=command.description.model_dump(),
            status="draft",
            version=1,
            image="",
            image_ready=False,
            image_kind="illustration",
            search_tokens=[],
        )
        self.db.add(product)
        await self.db.flush()
        await self.reindex(product)
        self.audit(
            product.id,
            "product.created",
            product.id,
            {},
            snapshot(product, CONTENT_FIELDS + ("status", "version")),
        )
        return product.id

    async def edit(self, product_id: UUID, command: ProductEdit) -> None:
        product = await self.product(product_id, command.expected_version)
        await self.category_exists(command.category_id)
        before = snapshot(product, CONTENT_FIELDS + ("version",))
        for field in CONTENT_FIELDS:
            value = getattr(command, field)
            setattr(product, field, value.model_dump() if field == "description" else value)
        if before == snapshot(product, CONTENT_FIELDS + ("version",)):
            return
        product.version += 1
        await self.reindex(product)
        self.audit(
            product.id,
            "product.edited",
            product.id,
            before,
            snapshot(product, CONTENT_FIELDS + ("version",)),
        )

    async def status(self, product_id: UUID, command: StatusChange) -> None:
        product = await self.product(product_id, command.expected_version)
        if command.status == product.status:
            return
        if command.status == "published":
            product = await read_product(self.db, product.id)
            if not product.image_ready or not product.image or not product.variants:
                raise AdministrationError(
                    "catalog.not_publishable", "A ready image and valid variant are required"
                )
            # Validate all stored variants; never turn unknown data into invented facts.
            ProductContent.model_validate(snapshot(product, CONTENT_FIELDS))
            for variant in product.variants:
                variant_contract(variant)
        before = snapshot(product, ("status", "version"))
        product.status = command.status
        product.version += 1
        self.audit(
            product.id,
            "product.status_changed",
            product.id,
            before,
            snapshot(product, ("status", "version")),
        )

    async def create_variant(self, product_id: UUID, command: VariantContent) -> None:
        product = await self.product(product_id, command.expected_version)
        count = await self.db.scalar(
            select(func.count()).select_from(VariantRow).where(VariantRow.product_id == product.id)
        )
        if count is not None and count >= 100:
            raise AdministrationError(
                "catalog.variant_limit", "A product supports at most 100 variants"
            )
        kind = command.specifications.kind
        variant = VariantRow(
            id=uuid4(),
            product_id=product.id,
            sku=command.sku,
            packaging=command.packaging.model_dump(),
            specifications=command.specifications.model_dump(mode="json"),
            evidence=[item.model_dump(mode="json") for item in command.evidence],
            stock_kind="stocked_prebuilt"
            if kind == "prebuilt"
            else "accessory"
            if kind == "peripheral"
            else "component",
            on_hand=0,
            reserved=0,
            stock_verified=False,
            version=1,
            spec_version=1,
        )
        self.db.add(variant)
        product.version += 1
        await self.db.flush()
        await self.reindex(product)
        self.audit(product.id, "variant.created", variant.id, {}, snapshot(variant, VARIANT_FIELDS))

    async def edit_variant(
        self, product_id: UUID, variant_id: UUID, command: VariantContent
    ) -> None:
        product = await self.product(product_id, command.expected_version)
        variant = await self.variant(product_id, variant_id)
        if command.specifications.kind != variant.specifications["kind"]:
            raise AdministrationError(
                "catalog.variant_kind_immutable",
                "Create a distinct variant for a different hardware kind",
            )
        before = snapshot(variant, VARIANT_FIELDS)
        variant.sku = command.sku
        variant.packaging = command.packaging.model_dump()
        variant.specifications = command.specifications.model_dump(mode="json")
        variant.evidence = [item.model_dump(mode="json") for item in command.evidence]
        if before == snapshot(variant, VARIANT_FIELDS):
            return
        variant.version += 1
        variant.spec_version += 1
        product.version += 1
        await self.reindex(product)
        self.audit(
            product.id, "variant.edited", variant.id, before, snapshot(variant, VARIANT_FIELDS)
        )

    async def stock(self, product_id: UUID, variant_id: UUID, command: StockChange) -> None:
        product = await self.product(product_id, command.expected_version)
        variant = await self.variant(product_id, variant_id)
        if variant.version != command.expected_stock_version:
            raise AdministrationError(
                "catalog.stock_version_conflict", "Stock changed; reload before adjusting"
            )
        if command.on_hand < variant.reserved:
            raise AdministrationError(
                "catalog.stock_reserved", "Physical stock cannot be lower than reserved stock"
            )
        fields = ("on_hand", "reserved", "stock_verified", "version")
        before = snapshot(variant, fields)
        if (variant.on_hand, variant.stock_verified) == (command.on_hand, command.stock_verified):
            return
        variant.on_hand, variant.stock_verified = command.on_hand, command.stock_verified
        variant.version += 1
        product.version += 1
        self.audit(
            product.id,
            "stock.adjusted",
            variant.id,
            before,
            snapshot(variant, fields),
            command.reason,
        )

    async def offer(self, product_id: UUID, variant_id: UUID, command: OfferChange) -> None:
        product = await self.product(product_id, command.expected_version)
        variant = await self.variant(product_id, variant_id)
        offer = await self.db.scalar(
            select(OfferRow)
            .where(
                OfferRow.variant_id == variant_id,
                OfferRow.market == command.market,
            )
            .with_for_update()
        )
        current = offer.price_version if offer else 0
        if current != command.expected_price_version:
            raise AdministrationError(
                "catalog.price_version_conflict", "Price changed; reload before editing"
            )
        if command.available_for_sale and (
            product.status != "published" or not product.image_ready or not variant.stock_verified
        ):
            raise AdministrationError(
                "catalog.offer_not_ready",
                "Sale eligibility requires a published product, ready image and verified stock",
            )
        before = snapshot(offer, OFFER_FIELDS) if offer else {}
        if offer is None:
            offer = OfferRow(id=uuid4(), variant_id=variant.id, price_version=0)
            self.db.add(offer)
        for field in OFFER_FIELDS:
            if field != "price_version":
                value = getattr(command, field)
                setattr(offer, field, value.model_dump(mode="json") if field == "source" else value)
        if before == snapshot(offer, OFFER_FIELDS):
            return
        offer.price_version = current + 1
        product.version += 1
        self.audit(
            product.id,
            "offer.changed",
            variant.id,
            before,
            snapshot(offer, OFFER_FIELDS),
            command.reason,
        )


@asynccontextmanager
async def transaction(
    db: AsyncSession, actor_id: UUID, request_id: str
) -> AsyncIterator[Administration]:
    try:
        async with db.begin():
            yield Administration(db, actor_id, request_id)
    except IntegrityError as exc:
        # Includes concurrent unique slug/SKU insertions. Never return SQL or submitted data.
        raise AdministrationError(
            "catalog.constraint_conflict", "The change conflicts with existing catalog data"
        ) from exc
