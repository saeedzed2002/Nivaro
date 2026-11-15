"""Retain the outcome of an unsuccessful paid reservation reallocation."""

import sqlalchemy as sa
from alembic import op

revision = "0009_paid_reservation"
down_revision = "0008_reservation_outbox"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "stock_reservations",
        sa.Column("paid_commit_rejected", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.create_check_constraint(
        "reservation_paid_rejection",
        "stock_reservations",
        "NOT paid_commit_rejected OR state = 'expired'",
    )


def downgrade() -> None:
    raise RuntimeError("Downgrading would discard paid reservation decisions")
