"""Keep the actor and original response for each operator refund retry."""

import sqlalchemy as sa
from alembic import op

revision = "0012_refund_operator_retries"
down_revision = "0011_order_delivered"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "order_refund_retries",
        sa.Column(
            "refund_id",
            sa.Uuid(),
            sa.ForeignKey("order_payment_compensations.refund_id", ondelete="RESTRICT"),
            primary_key=True,
        ),
        sa.Column("operation_id", sa.Uuid(), primary_key=True),
        sa.Column("actor_id", sa.Uuid(), nullable=False),
        sa.Column("expected_attempts", sa.Integer(), nullable=False),
        sa.Column("previous_error", sa.String(80)),
        sa.Column("queued_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("expected_attempts > 0", name="order_refund_retry_attempts"),
    )
    op.create_index(
        "ix_order_refund_retry_latest",
        "order_refund_retries",
        ["refund_id", "queued_at", "operation_id"],
    )


def downgrade() -> None:
    raise RuntimeError("Downgrading would discard staff refund retry audit records")
