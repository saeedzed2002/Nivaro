from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    Boolean,
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


class Timestamps:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


MARKET_CURRENCY = (
    "(market = 'ir' AND currency = 'IRR') OR (market = 'international' AND currency = 'USD')"
)


class CheckoutOperation(Timestamps, Base):
    __tablename__ = "checkout_operations"
    __table_args__ = (
        UniqueConstraint("customer_id", "idempotency_key", name="uq_checkout_customer_key"),
        CheckConstraint(
            "state IN ('started','pending_reservation','reservation_confirmed','reservation_failed')",
            name="checkout_state",
        ),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True)
    customer_id: Mapped[UUID] = mapped_column()
    idempotency_key: Mapped[str] = mapped_column(String(128))
    fingerprint: Mapped[str] = mapped_column(String(64))
    intent: Mapped[dict[str, Any]] = mapped_column(JSONB)
    state: Mapped[str] = mapped_column(String(24))


class CheckoutPreview(Base):
    __tablename__ = "checkout_previews"
    operation_id: Mapped[UUID] = mapped_column(
        ForeignKey("checkout_operations.id", ondelete="RESTRICT"), primary_key=True
    )
    quote_snapshot: Mapped[dict[str, Any]] = mapped_column(JSONB)
    address_fingerprint: Mapped[str] = mapped_column(String(64))
    totals_snapshot: Mapped[dict[str, Any]] = mapped_column(JSONB)
    confirmation: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Coupon(Timestamps, Base):
    __tablename__ = "coupons"
    __table_args__ = (
        UniqueConstraint("market", "code", name="uq_coupon_market_code"),
        CheckConstraint(MARKET_CURRENCY, name="coupon_market_currency"),
        CheckConstraint("code ~ '^[A-Z0-9][A-Z0-9_-]{0,39}$'", name="coupon_code"),
        CheckConstraint(
            "(kind = 'fixed' AND value > 0) OR (kind = 'percentage' AND value BETWEEN 1 AND 10000)",
            name="coupon_discount_bounds",
        ),
        CheckConstraint(
            "minimum_minor >= 0 AND (maximum_minor IS NULL OR maximum_minor > 0) AND "
            "global_limit >= per_customer_limit AND per_customer_limit > 0 AND starts_at < ends_at",
            name="coupon_policy_bounds",
        ),
        CheckConstraint(
            "currency <> 'IRR' OR ((kind <> 'fixed' OR value % 10 = 0) AND "
            "minimum_minor % 10 = 0 AND (maximum_minor IS NULL OR maximum_minor % 10 = 0))",
            name="coupon_whole_tomans",
        ),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(40))
    market: Mapped[str] = mapped_column(String(20))
    currency: Mapped[str] = mapped_column(String(3))
    kind: Mapped[str] = mapped_column(String(10))
    value: Mapped[int] = mapped_column(BigInteger)
    minimum_minor: Mapped[int] = mapped_column(BigInteger)
    maximum_minor: Mapped[int | None] = mapped_column(BigInteger)
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    global_limit: Mapped[int] = mapped_column(Integer)
    per_customer_limit: Mapped[int] = mapped_column(Integer)
    enabled: Mapped[bool] = mapped_column(Boolean)


class Order(Timestamps, Base):
    __tablename__ = "orders"
    __table_args__ = (
        CheckConstraint(MARKET_CURRENCY, name="order_market_currency"),
        CheckConstraint(
            "status IN ('pending_reservation','awaiting_payment','expired','cancelled',"
            "'payment_processing','payment_review','paid')",
            name="order_status",
        ),
        CheckConstraint("version > 0 AND cart_version > 0", name="order_versions"),
        CheckConstraint(
            "subtotal_minor > 0 AND discount_minor BETWEEN 0 AND subtotal_minor AND "
            "shipping_minor >= 0 AND tax_minor >= 0 AND total_minor >= 0 AND "
            "total_minor = subtotal_minor - discount_minor + shipping_minor + "
            "CASE WHEN tax_included THEN 0 ELSE tax_minor END",
            name="order_totals",
        ),
        CheckConstraint(
            "currency <> 'IRR' OR (subtotal_minor % 10 = 0 AND discount_minor % 10 = 0 "
            "AND shipping_minor % 10 = 0 AND tax_minor % 10 = 0 AND total_minor % 10 = 0)",
            name="order_whole_tomans",
        ),
        Index("ix_orders_customer_created", "customer_id", "created_at", "id"),
        Index(
            "ix_orders_pending_reservation",
            "reservation_retry_at",
            "created_at",
            "id",
            postgresql_where=text("status = 'pending_reservation'"),
        ),
        Index(
            "ix_orders_reservation_expiry",
            "reservation_expires_at",
            "id",
            postgresql_where=text("status = 'awaiting_payment'"),
        ),
        CheckConstraint("reservation_attempts >= 0", name="order_reservation_attempts"),
    )
    id: Mapped[UUID] = mapped_column(
        ForeignKey("checkout_operations.id", ondelete="RESTRICT"), primary_key=True
    )
    customer_id: Mapped[UUID] = mapped_column()
    status: Mapped[str] = mapped_column(String(24))
    version: Mapped[int] = mapped_column(Integer)
    cart_id: Mapped[UUID] = mapped_column()
    cart_version: Mapped[int] = mapped_column(Integer)
    cart_fingerprint: Mapped[str] = mapped_column(String(64))
    quote_id: Mapped[UUID] = mapped_column(unique=True)
    quote_expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    reservation_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reservation_retry_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reservation_attempts: Mapped[int] = mapped_column(Integer, server_default="0")
    reservation_error: Mapped[str | None] = mapped_column(String(80))
    confirmation: Mapped[str] = mapped_column(String(64))
    market: Mapped[str] = mapped_column(String(20))
    currency: Mapped[str] = mapped_column(String(3))
    subtotal_minor: Mapped[int] = mapped_column(BigInteger)
    discount_minor: Mapped[int] = mapped_column(BigInteger)
    shipping_minor: Mapped[int] = mapped_column(BigInteger)
    tax_minor: Mapped[int] = mapped_column(BigInteger)
    tax_included: Mapped[bool] = mapped_column(Boolean)
    total_minor: Mapped[int] = mapped_column(BigInteger)
    delivery_policy: Mapped[dict[str, Any]] = mapped_column(JSONB)


class OrderAddress(Base):
    __tablename__ = "order_address_snapshots"
    order_id: Mapped[UUID] = mapped_column(
        ForeignKey("orders.id", ondelete="RESTRICT"), primary_key=True
    )
    snapshot: Mapped[dict[str, Any]] = mapped_column(JSONB)


class OrderConfiguration(Base):
    __tablename__ = "order_configuration_snapshots"
    order_id: Mapped[UUID] = mapped_column(
        ForeignKey("orders.id", ondelete="RESTRICT"), primary_key=True
    )
    source_group_id: Mapped[UUID] = mapped_column(primary_key=True)
    snapshot: Mapped[dict[str, Any]] = mapped_column(JSONB)


class OrderItem(Base):
    __tablename__ = "order_items"
    __table_args__ = (
        ForeignKeyConstraint(
            ["order_id", "source_group_id"],
            [
                "order_configuration_snapshots.order_id",
                "order_configuration_snapshots.source_group_id",
            ],
            name="order_item_configuration",
        ),
        CheckConstraint(
            "quantity > 0 AND unit_price_minor > 0 AND source_line_version > 0",
            name="order_item_positive",
        ),
        CheckConstraint(
            "(source_group_id IS NULL) = (slot_key IS NULL)", name="order_item_slot_scope"
        ),
    )
    order_id: Mapped[UUID] = mapped_column(
        ForeignKey("orders.id", ondelete="RESTRICT"), primary_key=True
    )
    source_line_id: Mapped[UUID] = mapped_column(primary_key=True)
    source_line_version: Mapped[int] = mapped_column(Integer)
    source_group_id: Mapped[UUID | None] = mapped_column()
    slot_key: Mapped[str | None] = mapped_column(String(32))
    product_id: Mapped[UUID] = mapped_column()
    variant_id: Mapped[UUID] = mapped_column()
    sku: Mapped[str] = mapped_column(String(100))
    name: Mapped[str] = mapped_column(String(240))
    quantity: Mapped[int] = mapped_column(Integer)
    unit_price_minor: Mapped[int] = mapped_column(BigInteger)
    spec_version: Mapped[int] = mapped_column(Integer)
    specifications: Mapped[dict[str, Any]] = mapped_column(JSONB)
    price_version: Mapped[int] = mapped_column(Integer)


class CouponClaim(Base):
    __tablename__ = "coupon_claims"
    __table_args__ = (
        CheckConstraint(
            "state IN ('held','finalizing','consumed','released') AND amount_minor > 0",
            name="coupon_claim_state",
        ),
        Index("ix_coupon_claims_usage", "coupon_id", "state", "expires_at", "customer_id"),
    )
    order_id: Mapped[UUID] = mapped_column(
        ForeignKey("orders.id", ondelete="RESTRICT"), primary_key=True
    )
    coupon_id: Mapped[UUID] = mapped_column(ForeignKey("coupons.id", ondelete="RESTRICT"))
    customer_id: Mapped[UUID] = mapped_column()
    state: Mapped[str] = mapped_column(String(10))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    amount_minor: Mapped[int] = mapped_column(BigInteger)
    snapshot: Mapped[dict[str, Any]] = mapped_column(JSONB)


class OrderTransition(Base):
    __tablename__ = "order_transitions"
    order_id: Mapped[UUID] = mapped_column(
        ForeignKey("orders.id", ondelete="RESTRICT"), primary_key=True
    )
    version: Mapped[int] = mapped_column(Integer, primary_key=True)
    customer_id: Mapped[UUID] = mapped_column()
    status: Mapped[str] = mapped_column(String(24))
    reason: Mapped[str] = mapped_column(String(80))
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class InboxEvent(Base):
    __tablename__ = "event_inbox"
    consumer_name: Mapped[str] = mapped_column(String(80), primary_key=True)
    event_id: Mapped[UUID] = mapped_column(primary_key=True)
    aggregate_id: Mapped[UUID] = mapped_column()
    aggregate_version: Mapped[int] = mapped_column(Integer)
    processed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class OrderPaymentAttempt(Base):
    __tablename__ = "order_payment_attempts"
    __table_args__ = (
        ForeignKeyConstraint(
            ["order_id", "order_version"],
            ["order_transitions.order_id", "order_transitions.version"],
            name="order_payment_payable_transition",
        ),
        CheckConstraint(
            "(outcome IS NULL AND aggregate_version IS NULL AND verified_at IS NULL "
            "AND captured_minor IS NULL) OR "
            "(outcome IS NOT NULL AND aggregate_version IS NOT NULL AND aggregate_version > 0 "
            "AND verified_at IS NOT NULL AND ("
            "(outcome = 'payment.failed' AND captured_minor IS NULL) OR "
            "(outcome IN ('payment.succeeded', 'payment.amount_mismatch') "
            "AND captured_minor IS NOT NULL AND captured_minor > 0)))",
            name="order_payment_outcome",
        ),
        Index("ix_order_payment_attempts_order", "order_id", "order_version"),
        Index(
            "ix_order_payment_unhandled",
            "verified_at",
            "id",
            postgresql_where=text("disposition IS NULL AND captured_minor IS NOT NULL"),
        ),
        Index(
            "uq_order_payment_selected",
            "order_id",
            unique=True,
            postgresql_where=text("disposition = 'selected'"),
        ),
        Index(
            "ix_order_payment_stock_due",
            "stock_retry_at",
            "id",
            postgresql_where=text("stock_retry_at IS NOT NULL"),
        ),
        CheckConstraint(
            "stock_attempts >= 0 AND (stock_retry_at IS NULL OR disposition IS NOT DISTINCT FROM 'selected')",
            name="order_payment_stock_retry",
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True)
    order_id: Mapped[UUID] = mapped_column()
    order_version: Mapped[int] = mapped_column(Integer)
    outcome: Mapped[str | None] = mapped_column(String(30))
    aggregate_version: Mapped[int | None] = mapped_column(Integer)
    captured_minor: Mapped[int | None] = mapped_column(BigInteger)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    disposition: Mapped[str | None] = mapped_column(String(80))
    stock_retry_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    stock_attempts: Mapped[int] = mapped_column(Integer, server_default="0")


class OrderPaymentRefund(Base):
    __tablename__ = "order_payment_refunds"
    __table_args__ = (
        CheckConstraint("amount_minor > 0", name="order_payment_refund_amount"),
        Index("ix_order_payment_refunds_attempt", "payment_attempt_id"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True)
    payment_attempt_id: Mapped[UUID] = mapped_column(
        ForeignKey("order_payment_attempts.id", ondelete="RESTRICT")
    )
    amount_minor: Mapped[int] = mapped_column(BigInteger)
    completed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
