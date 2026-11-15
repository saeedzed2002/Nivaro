"""Commit reservation expiry and its event in one transaction."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0008_reservation_outbox"
down_revision = "0007_checkout_inventory"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "stock_reservations", sa.Column("version", sa.Integer(), nullable=False, server_default="1")
    )
    op.execute("UPDATE stock_reservations SET version = 2 WHERE state <> 'held'")
    op.create_check_constraint("reservation_version", "stock_reservations", "version > 0")
    op.create_table(
        "event_outbox",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("event_type", sa.String(80), nullable=False),
        sa.Column("aggregate_id", sa.Uuid(), nullable=False),
        sa.Column("aggregate_version", sa.Integer(), nullable=False),
        sa.Column("envelope", JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("available_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("lease_id", sa.Uuid()),
        sa.Column("lease_until", sa.DateTime(timezone=True)),
        sa.Column("published_at", sa.DateTime(timezone=True)),
        sa.Column("failed_at", sa.DateTime(timezone=True)),
        sa.Column("last_error", sa.String(80)),
        sa.UniqueConstraint(
            "event_type", "aggregate_id", "aggregate_version", name="uq_outbox_transition"
        ),
        sa.CheckConstraint("attempts >= 0", name="outbox_attempts"),
        sa.CheckConstraint("(lease_id IS NULL) = (lease_until IS NULL)", name="outbox_lease"),
        sa.CheckConstraint(
            "published_at IS NULL OR failed_at IS NULL", name="outbox_terminal_state"
        ),
    )
    op.create_index(
        "ix_outbox_pending",
        "event_outbox",
        ["available_at", "id"],
        postgresql_where=sa.text("published_at IS NULL AND failed_at IS NULL"),
    )


def downgrade() -> None:
    raise RuntimeError("Downgrading would discard durable reservation events")
