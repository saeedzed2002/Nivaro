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
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
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
    __table_args__ = (CheckConstraint("version > 0", name="category_version"),)
    id: Mapped[UUID] = mapped_column(primary_key=True)
    version: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
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
        CheckConstraint("version > 0", name="product_version"),
        Index("ix_products_search_tokens", "search_tokens", postgresql_using="gin"),
        Index("ix_products_status_category", "status", "category_id"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True)
    version: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
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


class DeliveredOrderRow(Base):
    __tablename__ = "delivered_order_inbox"

    event_id: Mapped[UUID] = mapped_column(primary_key=True)
    order_id: Mapped[UUID] = mapped_column(unique=True)
    fingerprint: Mapped[str] = mapped_column(String(64))


class PurchaseEntitlementRow(Base):
    __tablename__ = "purchase_entitlements"

    customer_id: Mapped[UUID] = mapped_column(primary_key=True)
    product_id: Mapped[UUID] = mapped_column(primary_key=True)
    first_delivered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


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


class QuoteRow(Timestamps, Base):
    __tablename__ = "checkout_quotes"
    id: Mapped[UUID] = mapped_column(primary_key=True)
    snapshot: Mapped[dict[str, Any]] = mapped_column(JSONB)


class ReservationRow(Timestamps, Base):
    __tablename__ = "stock_reservations"
    __table_args__ = (
        CheckConstraint(
            "state IN ('held','committed','released','expired')", name="reservation_state"
        ),
        CheckConstraint("version > 0", name="reservation_version"),
        CheckConstraint(
            "NOT paid_commit_rejected OR state = 'expired'", name="reservation_paid_rejection"
        ),
        Index(
            "ix_reservations_held_expiry",
            "expires_at",
            "operation_id",
            postgresql_where=text("state = 'held'"),
        ),
    )
    operation_id: Mapped[UUID] = mapped_column(primary_key=True)
    quote_id: Mapped[UUID] = mapped_column(
        ForeignKey("checkout_quotes.id", ondelete="RESTRICT"), unique=True
    )
    state: Mapped[str] = mapped_column(String(12))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    version: Mapped[int] = mapped_column(Integer, server_default="1")
    paid_commit_rejected: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))


class OutboxRow(Base):
    __tablename__ = "event_outbox"
    __table_args__ = (
        UniqueConstraint(
            "event_type", "aggregate_id", "aggregate_version", name="uq_outbox_transition"
        ),
        CheckConstraint("attempts >= 0", name="outbox_attempts"),
        CheckConstraint("(lease_id IS NULL) = (lease_until IS NULL)", name="outbox_lease"),
        CheckConstraint("published_at IS NULL OR failed_at IS NULL", name="outbox_terminal_state"),
        Index(
            "ix_outbox_pending",
            "available_at",
            "id",
            postgresql_where=text("published_at IS NULL AND failed_at IS NULL"),
        ),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True)
    event_type: Mapped[str] = mapped_column(String(80))
    aggregate_id: Mapped[UUID] = mapped_column()
    aggregate_version: Mapped[int] = mapped_column(Integer)
    envelope: Mapped[dict[str, Any]] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    available_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    attempts: Mapped[int] = mapped_column(Integer, server_default="0")
    lease_id: Mapped[UUID | None] = mapped_column()
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    failed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(String(80))


class AllocationRow(Base):
    __tablename__ = "stock_allocations"
    __table_args__ = (CheckConstraint("quantity > 0", name="allocation_quantity"),)
    operation_id: Mapped[UUID] = mapped_column(
        ForeignKey("stock_reservations.operation_id", ondelete="RESTRICT"), primary_key=True
    )
    variant_id: Mapped[UUID] = mapped_column(
        ForeignKey("variants.id", ondelete="RESTRICT"), primary_key=True, index=True
    )
    quantity: Mapped[int] = mapped_column(Integer)


class AuditRow(Base):
    __tablename__ = "catalog_audit_entries"
    __table_args__ = (Index("ix_catalog_audit_product_created", "product_id", "created_at", "id"),)
    id: Mapped[UUID] = mapped_column(primary_key=True)
    product_id: Mapped[UUID] = mapped_column(ForeignKey("products.id", ondelete="RESTRICT"))
    actor_id: Mapped[UUID] = mapped_column()
    action: Mapped[str] = mapped_column(String(60))
    target_id: Mapped[UUID] = mapped_column()
    before: Mapped[dict[str, Any]] = mapped_column(JSONB)
    after: Mapped[dict[str, Any]] = mapped_column(JSONB)
    reason: Mapped[str] = mapped_column(String(500))
    request_id: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class CategoryAuditRow(Base):
    __tablename__ = "category_audit_entries"
    __table_args__ = (Index("ix_category_audit_created", "category_id", "created_at", "id"),)
    id: Mapped[UUID] = mapped_column(primary_key=True)
    category_id: Mapped[UUID] = mapped_column(ForeignKey("categories.id", ondelete="RESTRICT"))
    actor_id: Mapped[UUID] = mapped_column()
    action: Mapped[str] = mapped_column(String(60))
    target_id: Mapped[UUID] = mapped_column()
    before: Mapped[dict[str, Any]] = mapped_column(JSONB)
    after: Mapped[dict[str, Any]] = mapped_column(JSONB)
    reason: Mapped[str] = mapped_column(String(500))
    request_id: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class MediaSlotRow(Base):
    __tablename__ = "product_media_slots"
    __table_args__ = (
        UniqueConstraint(
            "product_id",
            "position",
            name="media_slot_position",
            deferrable=True,
            initially="DEFERRED",
        ),
        CheckConstraint("position >= 0 AND position < 8", name="media_position_range"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True)
    product_id: Mapped[UUID] = mapped_column(ForeignKey("products.id", ondelete="RESTRICT"))
    position: Mapped[int] = mapped_column(Integer)
    alt: Mapped[dict[str, str]] = mapped_column(JSONB)
    desired_job_id: Mapped[UUID | None] = mapped_column()
    active_job_id: Mapped[UUID | None] = mapped_column()


class MediaJobRow(Base):
    __tablename__ = "product_media_jobs"
    __table_args__ = (
        CheckConstraint(
            "state IN ('uploaded','processing','ready','failed')", name="media_job_state"
        ),
        CheckConstraint("attempts >= 0 AND attempts <= 3", name="media_job_attempts"),
        Index("ix_media_job_recovery", "state", "lease_until"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True)
    slot_id: Mapped[UUID] = mapped_column(
        ForeignKey("product_media_slots.id", ondelete="RESTRICT"), index=True
    )
    actor_id: Mapped[UUID] = mapped_column()
    alt: Mapped[dict[str, str]] = mapped_column(JSONB)
    image_kind: Mapped[str] = mapped_column(String(20))
    state: Mapped[str] = mapped_column(String(20), default="uploaded")
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    attempt_id: Mapped[UUID | None] = mapped_column()
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    outputs: Mapped[dict[str, str]] = mapped_column(JSONB, default=dict)
    error_code: Mapped[str | None] = mapped_column(String(80))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class MediaDispatchRow(Base):
    __tablename__ = "product_media_dispatch"
    job_id: Mapped[UUID] = mapped_column(
        ForeignKey("product_media_jobs.id", ondelete="RESTRICT"), primary_key=True
    )
    available_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
    claim_id: Mapped[UUID | None] = mapped_column()
    claimed_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class PublicCacheGeneration(Base):
    __tablename__ = "public_cache_generation"
    __table_args__ = (CheckConstraint("id = 1", name="public_cache_singleton"),)
    id: Mapped[int] = mapped_column(SmallInteger, primary_key=True, autoincrement=False)
    token: Mapped[UUID] = mapped_column()
