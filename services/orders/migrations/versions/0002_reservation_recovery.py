"""Persist reservation recovery scheduling and catalog deadlines."""

import sqlalchemy as sa
from alembic import op

revision = "0002_reservation_recovery"
down_revision = "0001_orders"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint("checkout_state", "checkout_operations", type_="check")
    op.create_check_constraint(
        "checkout_state",
        "checkout_operations",
        "state IN ('started','pending_reservation','reservation_confirmed','reservation_failed')",
    )
    op.add_column("orders", sa.Column("reservation_expires_at", sa.DateTime(timezone=True)))
    op.add_column("orders", sa.Column("reservation_retry_at", sa.DateTime(timezone=True)))
    op.add_column(
        "orders",
        sa.Column("reservation_attempts", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column("orders", sa.Column("reservation_error", sa.String(80)))
    op.create_check_constraint("order_reservation_attempts", "orders", "reservation_attempts >= 0")
    op.create_index(
        "ix_orders_pending_reservation",
        "orders",
        ["reservation_retry_at", "created_at", "id"],
        postgresql_where=sa.text("status = 'pending_reservation'"),
    )
    op.create_index(
        "ix_orders_reservation_expiry",
        "orders",
        ["reservation_expires_at", "id"],
        postgresql_where=sa.text("status = 'awaiting_payment'"),
    )


def downgrade() -> None:
    raise RuntimeError("Downgrading would discard reservation recovery state")
