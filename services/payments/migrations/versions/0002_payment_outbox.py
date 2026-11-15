"""Persist payment outcomes and due reconciliation work."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0002_payment_outbox"
down_revision = "0001_payment_attempts"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("payment_attempts", sa.Column("reconcile_at", sa.DateTime(timezone=True)))
    op.add_column(
        "payment_attempts",
        sa.Column("reconciliation_attempts", sa.Integer(), nullable=False, server_default="0"),
    )
    op.create_check_constraint(
        "payment_reconciliation_attempts", "payment_attempts", "reconciliation_attempts >= 0"
    )
    op.create_index(
        "ix_payment_reconciliation_due",
        "payment_attempts",
        ["reconcile_at", "id"],
        postgresql_where=sa.text("reconcile_at IS NOT NULL"),
    )
    op.execute(
        "UPDATE payment_attempts SET reconcile_at = clock_timestamp() WHERE status = 'ambiguous'"
    )
    op.create_table(
        "event_outbox",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("event_type", sa.String(80), nullable=False),
        sa.Column("aggregate_id", sa.Uuid(), nullable=False),
        sa.Column("aggregate_version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("envelope", JSONB(), nullable=False),
        sa.UniqueConstraint(
            "event_type", "aggregate_id", "aggregate_version", name="uq_payment_outbox_transition"
        ),
    )


def downgrade() -> None:
    raise RuntimeError("Downgrading would discard payment outcomes and reconciliation work")
