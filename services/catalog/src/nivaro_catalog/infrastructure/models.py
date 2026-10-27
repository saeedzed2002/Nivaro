from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Timestamps:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class CategoryRow(Timestamps, Base):
    __tablename__ = "categories"
    id: Mapped[UUID] = mapped_column(primary_key=True)
    slug: Mapped[str] = mapped_column(String(80), unique=True)
    name: Mapped[dict[str, str]] = mapped_column(JSONB)
    image: Mapped[str] = mapped_column(String(100))
    parent_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("categories.id", ondelete="RESTRICT"), index=True
    )


class ProductRow(Timestamps, Base):
    __tablename__ = "products"
    __table_args__ = (
        CheckConstraint("status IN ('draft','published','archived')", name="product_status"),
        Index("ix_products_search_tokens", "search_tokens", postgresql_using="gin"),
        Index("ix_products_status_category", "status", "category_id"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True)
    slug: Mapped[str] = mapped_column(String(160), unique=True)
    name: Mapped[str] = mapped_column(String(240))
    description: Mapped[dict[str, str]] = mapped_column(JSONB)
    category_id: Mapped[UUID] = mapped_column(ForeignKey("categories.id", ondelete="RESTRICT"))
    brand: Mapped[str] = mapped_column(String(120), index=True)
    status: Mapped[str] = mapped_column(String(20), default="draft")
    image: Mapped[str] = mapped_column(String(100))
    image_ready: Mapped[bool] = mapped_column(Boolean, default=False)
    image_kind: Mapped[str] = mapped_column(String(20), default="illustration")
    highlights: Mapped[list[str]] = mapped_column(ARRAY(Text))
    search_tokens: Mapped[list[str]] = mapped_column(ARRAY(Text))
    category: Mapped[CategoryRow] = relationship(lazy="raise")
    variants: Mapped[list["VariantRow"]] = relationship(lazy="raise")


class VariantRow(Timestamps, Base):
    __tablename__ = "variants"
    __table_args__ = (
        CheckConstraint(
            "jsonb_typeof(specifications->'kind') = 'string' AND specifications->>'kind' IN ('cpu','motherboard','memory','storage','case','psu','cooler','gpu','peripheral','prebuilt')",
            name="spec_kind_known",
        ),
        CheckConstraint(
            "on_hand >= 0 AND reserved >= 0 AND reserved <= on_hand", name="variant_stock"
        ),
        CheckConstraint("spec_version > 0 AND version > 0", name="variant_versions"),
        CheckConstraint(
            "stock_kind IN ('component','accessory','stocked_prebuilt')", name="variant_stock_kind"
        ),
        CheckConstraint(
            "(stock_kind = 'stocked_prebuilt') = (specifications->>'kind' = 'prebuilt')",
            name="prebuilt_stock_isolation",
        ),
        CheckConstraint(
            "(stock_kind = 'accessory') = (specifications->>'kind' = 'peripheral')",
            name="accessory_stock_kind",
        ),
        CheckConstraint(
            "jsonb_typeof(specifications) = 'object' AND specifications ? 'kind'",
            name="typed_specs_required",
        ),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True)
    product_id: Mapped[UUID] = mapped_column(
        ForeignKey("products.id", ondelete="RESTRICT"), index=True
    )
    sku: Mapped[str] = mapped_column(String(100), unique=True)
    packaging: Mapped[dict[str, str]] = mapped_column(JSONB)
    specifications: Mapped[dict[str, Any]] = mapped_column(JSONB)
    spec_version: Mapped[int] = mapped_column(Integer, default=1)
    evidence: Mapped[list[dict[str, Any]]] = mapped_column(JSONB)
    stock_kind: Mapped[str] = mapped_column(String(30))
    on_hand: Mapped[int] = mapped_column(BigInteger, default=0)
    reserved: Mapped[int] = mapped_column(BigInteger, default=0)
    stock_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    version: Mapped[int] = mapped_column(Integer, default=1)
    offers: Mapped[list["OfferRow"]] = relationship(lazy="raise")


class OfferRow(Timestamps, Base):
    __tablename__ = "market_offers"
    __table_args__ = (
        UniqueConstraint("variant_id", "market", name="uq_variant_market"),
        CheckConstraint(
            "(market = 'ir' AND currency = 'IRR') OR (market = 'international' AND currency = 'USD')",
            name="offer_market_currency",
        ),
        CheckConstraint(
            "amount_minor > 0 AND amount_minor <= 9000000000000 AND (currency <> 'IRR' OR amount_minor % 10 = 0)",
            name="offer_amount",
        ),
        CheckConstraint("price_version > 0", name="offer_version"),
        CheckConstraint(
            "NOT (reference_only AND available_for_sale)", name="reference_not_sellable"
        ),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True)
    variant_id: Mapped[UUID] = mapped_column(
        ForeignKey("variants.id", ondelete="RESTRICT"), index=True
    )
    market: Mapped[str] = mapped_column(String(20))
    currency: Mapped[str] = mapped_column(String(3))
    amount_minor: Mapped[int] = mapped_column(BigInteger)
    price_version: Mapped[int] = mapped_column(Integer, default=1)
    available_for_sale: Mapped[bool] = mapped_column(Boolean, default=False)
    reference_only: Mapped[bool] = mapped_column(Boolean, default=True)
    source: Mapped[dict[str, Any]] = mapped_column(JSONB)
    seller: Mapped[str] = mapped_column(String(120))
