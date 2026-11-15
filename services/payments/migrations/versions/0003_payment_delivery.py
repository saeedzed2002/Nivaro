"""Track payment outbox deliveries and retain existing events for publication."""

import sqlalchemy as sa
from alembic import op

revision = "0003_payment_delivery"
down_revision = "0002_payment_outbox"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("event_outbox", sa.Column("available_at", sa.DateTime(timezone=True)))
    op.execute("UPDATE event_outbox SET available_at = created_at")
    op.alter_column("event_outbox", "available_at", nullable=False)
    op.add_column(
        "event_outbox", sa.Column("attempts", sa.Integer(), nullable=False, server_default="0")
    )
    op.add_column("event_outbox", sa.Column("lease_id", sa.Uuid()))
    for field in ("lease_until", "published_at", "failed_at"):
        op.add_column("event_outbox", sa.Column(field, sa.DateTime(timezone=True)))
    op.add_column("event_outbox", sa.Column("last_error", sa.String(80)))
    op.create_check_constraint("payment_outbox_attempts", "event_outbox", "attempts >= 0")
    op.create_check_constraint(
        "payment_outbox_lease", "event_outbox", "(lease_id IS NULL) = (lease_until IS NULL)"
    )
    op.create_check_constraint(
        "payment_outbox_terminal", "event_outbox", "published_at IS NULL OR failed_at IS NULL"
    )
    op.create_index(
        "ix_payment_outbox_due",
        "event_outbox",
        ["available_at", "id"],
        postgresql_where=sa.text("published_at IS NULL AND failed_at IS NULL"),
    )


def downgrade() -> None:
    raise RuntimeError("Downgrading would discard payment delivery history")
