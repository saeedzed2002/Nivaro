"""Keep verified payment attempts and refunds against their payable order revision."""

import sqlalchemy as sa
from alembic import op

revision = "0005_order_payment_results"
down_revision = "0004_checkout_previews"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "order_payment_attempts",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("order_id", sa.Uuid(), nullable=False),
        sa.Column("order_version", sa.Integer(), nullable=False),
        sa.Column("outcome", sa.String(30)),
        sa.Column("aggregate_version", sa.Integer()),
        sa.Column("captured_minor", sa.BigInteger()),
        sa.Column("verified_at", sa.DateTime(timezone=True)),
        sa.ForeignKeyConstraint(
            ["order_id", "order_version"],
            ["order_transitions.order_id", "order_transitions.version"],
            name="order_payment_payable_transition",
        ),
        sa.CheckConstraint(
            "(outcome IS NULL AND aggregate_version IS NULL AND verified_at IS NULL "
            "AND captured_minor IS NULL) OR "
            "(outcome IS NOT NULL AND aggregate_version IS NOT NULL AND aggregate_version > 0 "
            "AND verified_at IS NOT NULL AND ("
            "(outcome = 'payment.failed' AND captured_minor IS NULL) OR "
            "(outcome IN ('payment.succeeded', 'payment.amount_mismatch') "
            "AND captured_minor IS NOT NULL AND captured_minor > 0)))",
            name="order_payment_outcome",
        ),
    )
    op.create_index(
        "ix_order_payment_attempts_order", "order_payment_attempts", ["order_id", "order_version"]
    )
    op.create_table(
        "order_payment_refunds",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "payment_attempt_id",
            sa.Uuid(),
            sa.ForeignKey("order_payment_attempts.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("amount_minor", sa.BigInteger(), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("amount_minor > 0", name="order_payment_refund_amount"),
    )
    op.create_index(
        "ix_order_payment_refunds_attempt", "order_payment_refunds", ["payment_attempt_id"]
    )


def downgrade() -> None:
    raise RuntimeError("Downgrading would discard verified payment results")
