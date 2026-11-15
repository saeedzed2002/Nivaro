from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from nivaro_payments.contracts import AttemptState, Currency, Market, Scenario


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
