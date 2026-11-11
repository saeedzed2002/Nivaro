"""Cart ownership, stable component lines and revisioned build snapshots."""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Owner(Base):
    __tablename__ = "owners"
    __table_args__ = (
        CheckConstraint(
            "(customer_id IS NOT NULL AND guest_digest IS NULL) OR (customer_id IS NULL AND guest_digest IS NOT NULL)",
            name="owner_one_identity",
        ),
        CheckConstraint(
            "guest_csrf IS NULL OR (guest_digest IS NOT NULL AND char_length(guest_csrf) = 43)",
            name="owner_guest_csrf",
        ),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    customer_id: Mapped[UUID | None] = mapped_column(unique=True)
    guest_digest: Mapped[str | None] = mapped_column(String(64), unique=True)
    guest_csrf: Mapped[str | None] = mapped_column(String(43))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_active_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )


class Cart(Base):
    __tablename__ = "carts"
    __table_args__ = (
        UniqueConstraint("owner_id", "market", name="cart_owner_market"),
        CheckConstraint(
            "(market = 'ir' AND currency = 'IRR') OR (market = 'international' AND currency = 'USD')",
            name="cart_market_currency",
        ),
        CheckConstraint("version > 0", name="cart_version"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    owner_id: Mapped[UUID] = mapped_column(ForeignKey("owners.id", ondelete="RESTRICT"))
    market: Mapped[str] = mapped_column(String(16))
    currency: Mapped[str] = mapped_column(String(3))
    version: Mapped[int] = mapped_column(Integer, default=1)


class Build(Base):
    __tablename__ = "builds"
    __table_args__ = (
        CheckConstraint("version > 0", name="build_version"),
        CheckConstraint("mode IN ('complete_build','parts_only')", name="build_mode"),
        CheckConstraint(
            "(market = 'ir' AND currency = 'IRR') OR (market = 'international' AND currency = 'USD')",
            name="build_market_currency",
        ),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    owner_id: Mapped[UUID] = mapped_column(ForeignKey("owners.id", ondelete="RESTRICT"), index=True)
    name: Mapped[str] = mapped_column(String(100))
    market: Mapped[str] = mapped_column(String(16))
    currency: Mapped[str] = mapped_column(String(3))
    mode: Mapped[str] = mapped_column(String(20), default="complete_build")
    version: Mapped[int] = mapped_column(Integer, default=1)


class BuildLine(Base):
    __tablename__ = "build_lines"
    __table_args__ = (
        UniqueConstraint("build_id", "slot_key", name="build_slot"),
        CheckConstraint("quantity > 0", name="build_quantity"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    build_id: Mapped[UUID] = mapped_column(ForeignKey("builds.id", ondelete="CASCADE"))
    slot_key: Mapped[str] = mapped_column(String(64))
    variant_id: Mapped[UUID] = mapped_column()
    quantity: Mapped[int] = mapped_column(Integer)


class CartGroup(Base):
    __tablename__ = "cart_groups"
    __table_args__ = (
        UniqueConstraint("cart_id", "id", name="group_cart_identity"),
        CheckConstraint("version > 0", name="group_version"),
        CheckConstraint("mode IN ('complete_build','parts_only')", name="group_mode"),
        CheckConstraint(
            "(source_build_id IS NULL AND source_build_version IS NULL) OR (source_build_id IS NOT NULL AND source_build_version IS NOT NULL AND source_build_version > 0)",
            name="group_source_snapshot",
        ),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    cart_id: Mapped[UUID] = mapped_column(ForeignKey("carts.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(100))
    mode: Mapped[str] = mapped_column(String(20), default="complete_build")
    version: Mapped[int] = mapped_column(Integer, default=1)
    # Snapshot provenance survives deletion of the original editable draft.
    source_build_id: Mapped[UUID | None] = mapped_column()
    source_build_version: Mapped[int | None] = mapped_column(Integer)


class CartLine(Base):
    __tablename__ = "cart_lines"
    __table_args__ = (
        ForeignKeyConstraint(
            ["cart_id", "group_id"], ["cart_groups.cart_id", "cart_groups.id"], ondelete="CASCADE"
        ),
        UniqueConstraint("cart_id", "group_id", "slot_key", name="cart_group_slot"),
        Index(
            "standalone_variant",
            "cart_id",
            "variant_id",
            unique=True,
            postgresql_where=text("group_id IS NULL"),
        ),
        CheckConstraint("quantity > 0 AND version > 0", name="line_bounds"),
        CheckConstraint(
            "(observed_price_minor IS NULL AND observed_price_version IS NULL) OR "
            "(observed_price_minor IS NOT NULL AND observed_price_version IS NOT NULL AND "
            "observed_price_minor > 0 AND observed_price_version > 0)",
            name="line_observed_price",
        ),
        CheckConstraint(
            "(group_id IS NULL AND slot_key IS NULL) OR (group_id IS NOT NULL AND slot_key IS NOT NULL)",
            name="line_slot_scope",
        ),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    cart_id: Mapped[UUID] = mapped_column(ForeignKey("carts.id", ondelete="CASCADE"), index=True)
    group_id: Mapped[UUID | None] = mapped_column()
    slot_key: Mapped[str | None] = mapped_column(String(64))
    variant_id: Mapped[UUID] = mapped_column()
    quantity: Mapped[int] = mapped_column(Integer)
    version: Mapped[int] = mapped_column(Integer, default=1)
    observed_price_minor: Mapped[int | None] = mapped_column(BigInteger)
    observed_price_version: Mapped[int | None] = mapped_column(Integer)


class Operation(Base):
    __tablename__ = "operations"
    __table_args__ = (
        UniqueConstraint("owner_id", "kind", "key", name="operation_replay_identity"),
        CheckConstraint("kind IN ('merge','transfer','paid_cleanup')", name="operation_kind"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    owner_id: Mapped[UUID] = mapped_column(ForeignKey("owners.id", ondelete="RESTRICT"))
    kind: Mapped[str] = mapped_column(String(20))
    key: Mapped[str] = mapped_column(String(128))
    fingerprint: Mapped[str] = mapped_column(String(64))
    result: Mapped[dict[str, object]] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
