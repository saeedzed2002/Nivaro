from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from nivaro_payments.contracts import AttemptState, Currency, Market, ReconciliationResult, Scenario


class Base(DeclarativeBase):
    pass


class Attempt(Base):
    __tablename__ = "payment_attempts"
    __table_args__ = (
        UniqueConstraint("idempotency_key", name="uq_payment_key"),
        UniqueConstraint("provider_reference", name="uq_payment_provider_reference"),
        CheckConstraint(
            "(market = 'ir' AND currency = 'IRR') OR (market = 'international' AND currency = 'USD')",
            name="payment_market",
        ),
        CheckConstraint(
            "amount_minor > 0 AND (currency <> 'IRR' OR amount_minor % 10 = 0)",
            name="payment_amount",
        ),
        CheckConstraint("order_version > 0 AND version > 0", name="payment_versions"),
        CheckConstraint("reconciliation_attempts >= 0", name="payment_reconciliation_attempts"),
        Index("ix_payment_attempts_created", "created_at", "id"),
        Index(
            "ix_payment_reconciliation_due",
            "reconcile_at",
            "id",
            postgresql_where=text("reconcile_at IS NOT NULL"),
        ),
        CheckConstraint(
            "(status IN ('pending', 'ambiguous') AND verified_at IS NULL AND captured_minor IS NULL) OR "
            "(status = 'failed' AND verified_at IS NOT NULL AND captured_minor IS NULL) OR "
            "(status = 'succeeded' AND verified_at IS NOT NULL AND captured_minor IS NOT NULL AND captured_minor = amount_minor) OR "
            "(status = 'amount_mismatch' AND verified_at IS NOT NULL AND captured_minor IS NOT NULL AND captured_minor > 0 AND captured_minor <> amount_minor)",
            name="payment_outcome",
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True)
    idempotency_key: Mapped[str] = mapped_column(String(128))
    fingerprint: Mapped[str] = mapped_column(String(64))
    order_id: Mapped[UUID] = mapped_column(index=True)
    order_version: Mapped[int]
    market: Mapped[Market] = mapped_column(String(20))
    currency: Mapped[Currency] = mapped_column(String(3))
    amount_minor: Mapped[int] = mapped_column(BigInteger)
    reservation_expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    scenario: Mapped[Scenario] = mapped_column(String(16))
    provider_reference: Mapped[str] = mapped_column(String(80))
    status: Mapped[AttemptState] = mapped_column(String(24))
    version: Mapped[int]
    captured_minor: Mapped[int | None] = mapped_column(BigInteger)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reconcile_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reconciliation_attempts: Mapped[int] = mapped_column(server_default="0")


class ReconciliationRun(Base):
    __tablename__ = "reconciliation_runs"
    __table_args__ = (
        Index("ix_reconciliation_runs_attempt_time", "attempt_id", "checked_at", "operation_id"),
    )

    attempt_id: Mapped[UUID] = mapped_column(
        ForeignKey("payment_attempts.id", ondelete="RESTRICT"), primary_key=True
    )
    operation_id: Mapped[UUID] = mapped_column(primary_key=True)
    actor_id: Mapped[UUID]
    checked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    status_before: Mapped[AttemptState] = mapped_column(String(24))
    status_after: Mapped[AttemptState] = mapped_column(String(24))
    result: Mapped[ReconciliationResult] = mapped_column(String(24))


class Refund(Base):
    __tablename__ = "refund_requests"
    __table_args__ = (
        UniqueConstraint("idempotency_key", name="uq_refund_key"),
        UniqueConstraint("provider_reference", name="uq_refund_provider_reference"),
        CheckConstraint(
            "currency IN ('IRR', 'USD') AND amount_minor > 0 AND (currency <> 'IRR' OR amount_minor % 10 = 0)",
            name="refund_amount",
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True)
    payment_id: Mapped[UUID] = mapped_column(
        ForeignKey("payment_attempts.id", ondelete="RESTRICT"), index=True
    )
    idempotency_key: Mapped[str] = mapped_column(String(128))
    fingerprint: Mapped[str] = mapped_column(String(64))
    currency: Mapped[Currency] = mapped_column(String(3))
    amount_minor: Mapped[int] = mapped_column(BigInteger)
    reason: Mapped[str] = mapped_column(String(80))
    provider_reference: Mapped[str] = mapped_column(String(80))
    completed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class OutboxEvent(Base):
    __tablename__ = "event_outbox"
    __table_args__ = (
        UniqueConstraint(
            "event_type", "aggregate_id", "aggregate_version", name="uq_payment_outbox_transition"
        ),
        CheckConstraint("attempts >= 0", name="payment_outbox_attempts"),
        CheckConstraint("(lease_id IS NULL) = (lease_until IS NULL)", name="payment_outbox_lease"),
        CheckConstraint(
            "published_at IS NULL OR failed_at IS NULL", name="payment_outbox_terminal"
        ),
        Index(
            "ix_payment_outbox_due",
            "available_at",
            "id",
            postgresql_where=text("published_at IS NULL AND failed_at IS NULL"),
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True)
    event_type: Mapped[str] = mapped_column(String(80))
    aggregate_id: Mapped[UUID]
    aggregate_version: Mapped[int]
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    available_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    attempts: Mapped[int] = mapped_column(server_default="0")
    lease_id: Mapped[UUID | None]
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    failed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(String(80))
    envelope: Mapped[dict[str, Any]] = mapped_column(JSONB)
