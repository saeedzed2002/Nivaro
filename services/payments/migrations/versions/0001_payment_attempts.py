"""Create private payment attempts and simulated refund records."""

import sqlalchemy as sa
from alembic import op

revision = "0001_payment_attempts"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "payment_attempts",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("fingerprint", sa.String(64), nullable=False),
        sa.Column("order_id", sa.Uuid(), nullable=False),
        sa.Column("order_version", sa.Integer(), nullable=False),
        sa.Column("market", sa.String(20), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("amount_minor", sa.BigInteger(), nullable=False),
        sa.Column("reservation_expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("scenario", sa.String(16), nullable=False),
        sa.Column("provider_reference", sa.String(80), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("captured_minor", sa.BigInteger()),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("verified_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("idempotency_key", name="uq_payment_key"),
        sa.UniqueConstraint("provider_reference", name="uq_payment_provider_reference"),
        sa.CheckConstraint(
            "(market = 'ir' AND currency = 'IRR') OR (market = 'international' AND currency = 'USD')",
            name="payment_market",
        ),
        sa.CheckConstraint(
            "amount_minor > 0 AND (currency <> 'IRR' OR amount_minor % 10 = 0)",
            name="payment_amount",
        ),
        sa.CheckConstraint("order_version > 0 AND version > 0", name="payment_versions"),
        sa.CheckConstraint(
            "(status IN ('pending', 'ambiguous') AND verified_at IS NULL AND captured_minor IS NULL) OR "
            "(status = 'failed' AND verified_at IS NOT NULL AND captured_minor IS NULL) OR "
            "(status = 'succeeded' AND verified_at IS NOT NULL AND captured_minor IS NOT NULL AND captured_minor = amount_minor) OR "
            "(status = 'amount_mismatch' AND verified_at IS NOT NULL AND captured_minor IS NOT NULL AND captured_minor > 0 AND captured_minor <> amount_minor)",
            name="payment_outcome",
        ),
    )
    op.create_index("ix_payment_attempts_order_id", "payment_attempts", ["order_id"])
    op.create_table(
        "refund_requests",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "payment_id",
            sa.Uuid(),
            sa.ForeignKey("payment_attempts.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("fingerprint", sa.String(64), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("amount_minor", sa.BigInteger(), nullable=False),
        sa.Column("reason", sa.String(80), nullable=False),
        sa.Column("provider_reference", sa.String(80), nullable=False),
        sa.Column(
            "completed_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint("idempotency_key", name="uq_refund_key"),
        sa.UniqueConstraint("provider_reference", name="uq_refund_provider_reference"),
        sa.CheckConstraint(
            "currency IN ('IRR', 'USD') AND amount_minor > 0 AND (currency <> 'IRR' OR amount_minor % 10 = 0)",
            name="refund_amount",
        ),
    )
    op.create_index("ix_refund_requests_payment_id", "refund_requests", ["payment_id"])


def downgrade() -> None:
    raise RuntimeError("Downgrading would discard payment and refund records")
