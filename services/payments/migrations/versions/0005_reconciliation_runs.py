"""Persist operator reconciliation and its repeatable outcome."""

import sqlalchemy as sa
from alembic import op

revision = "0005_reconciliation_runs"
down_revision = "0004_payment_operations"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "reconciliation_runs",
        sa.Column(
            "attempt_id",
            sa.Uuid(),
            sa.ForeignKey("payment_attempts.id", ondelete="RESTRICT"),
            primary_key=True,
        ),
        sa.Column("operation_id", sa.Uuid(), primary_key=True),
        sa.Column("actor_id", sa.Uuid(), nullable=False),
        sa.Column("checked_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status_before", sa.String(24), nullable=False),
        sa.Column("status_after", sa.String(24), nullable=False),
        sa.Column("result", sa.String(24), nullable=False),
    )
    op.create_index(
        "ix_reconciliation_runs_attempt_time",
        "reconciliation_runs",
        ["attempt_id", "checked_at", "operation_id"],
    )


def downgrade() -> None:
    raise RuntimeError("Downgrading would discard operator reconciliation records")
