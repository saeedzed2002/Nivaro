"""Persist the customer's explicit request to pay the reviewed order."""

import sqlalchemy as sa
from alembic import op

revision = "0008_payment_initiations"
down_revision = "0007_payment_compensation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    table = "order_payment_initiations"
    op.create_table(
        table,
        sa.Column("order_id", sa.Uuid(), primary_key=True),
        sa.Column("order_version", sa.Integer(), nullable=False),
        sa.Column("attempt_id", sa.Uuid(), nullable=False, unique=True),
        sa.Column("reservation_expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("state", sa.String(12), nullable=False),
        sa.Column("retry_at", sa.DateTime(timezone=True)),
        sa.Column("attempts", sa.Integer(), server_default="0", nullable=False),
        sa.ForeignKeyConstraint(
            ["order_id", "order_version"],
            ["order_transitions.order_id", "order_transitions.version"],
            name="order_payment_initiation_version",
        ),
        sa.CheckConstraint(
            "state IN ('queued','submitted','blocked') AND attempts >= 0 "
            "AND (state = 'queued') = (retry_at IS NOT NULL)",
            name="order_payment_initiation_state",
        ),
    )
    op.create_index(
        "ix_order_payment_initiations_due",
        table,
        ["retry_at", "order_id"],
        postgresql_where=sa.text("retry_at IS NOT NULL"),
    )


def downgrade() -> None:
    raise RuntimeError("Downgrading would discard authorized payment requests")
