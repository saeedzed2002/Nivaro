"""Deduplicate consumed reservation expiry events transactionally."""

import sqlalchemy as sa
from alembic import op

revision = "0003_reservation_inbox"
down_revision = "0002_reservation_recovery"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "event_inbox",
        sa.Column("consumer_name", sa.String(80), primary_key=True),
        sa.Column("event_id", sa.Uuid(), primary_key=True),
        sa.Column("aggregate_id", sa.Uuid(), nullable=False),
        sa.Column("aggregate_version", sa.Integer(), nullable=False),
        sa.Column(
            "processed_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )


def downgrade() -> None:
    raise RuntimeError("Downgrading would discard processed event identifiers")
