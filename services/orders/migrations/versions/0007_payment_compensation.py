"""Persist refund intents and their independently verified outcomes."""

import sqlalchemy as sa
from alembic import op

revision = "0007_payment_compensation"
down_revision = "0006_payment_stock_commit"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint("order_status", "orders", type_="check")
    op.create_check_constraint(
        "order_status",
        "orders",
        "status IN ('pending_reservation','awaiting_payment','expired','cancelled',"
        "'payment_processing','payment_review','paid','refund_pending','refunded')",
    )
    op.create_table(
        "order_payment_compensations",
        sa.Column(
            "attempt_id",
            sa.Uuid(),
            sa.ForeignKey("order_payment_attempts.id", ondelete="RESTRICT"),
            primary_key=True,
        ),
        sa.Column("refund_id", sa.Uuid(), nullable=False, unique=True),
        sa.Column("captured_minor", sa.BigInteger(), nullable=False),
        sa.Column("closes_order", sa.Boolean(), nullable=False),
        sa.Column("reason", sa.String(80), nullable=False),
        sa.Column("state", sa.String(20), nullable=False),
        sa.Column("retry_at", sa.DateTime(timezone=True)),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_error", sa.String(80)),
        sa.CheckConstraint(
            "state IN ('pending','awaiting_evidence','completed','manual_review') "
            "AND captured_minor > 0 AND attempts >= 0 AND (state = 'pending') = (retry_at IS NOT NULL)",
            name="order_compensation_state",
        ),
    )
    op.create_index(
        "ix_order_compensation_due",
        "order_payment_compensations",
        ["retry_at", "attempt_id"],
        postgresql_where=sa.text("retry_at IS NOT NULL"),
    )


def downgrade() -> None:
    raise RuntimeError("Downgrading would discard compensation history")
