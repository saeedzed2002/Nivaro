"""Add audited fulfillment states and a shipment reference."""

import sqlalchemy as sa
from alembic import op

revision = "0010_order_fulfillment"
down_revision = "0009_order_paid_outbox"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("orders", sa.Column("tracking_reference", sa.String(80)))
    op.add_column("order_transitions", sa.Column("staff_actor_id", sa.Uuid()))
    op.drop_constraint("order_status", "orders", type_="check")
    op.create_check_constraint(
        "order_status",
        "orders",
        "status IN ('pending_reservation','awaiting_payment','expired','cancelled',"
        "'payment_processing','payment_review','paid','refund_pending','refunded','processing','shipped','delivered')",
    )
    op.create_check_constraint(
        "order_tracking_state",
        "orders",
        "(status IN ('shipped','delivered')) = (tracking_reference IS NOT NULL)",
    )
    op.create_index("ix_orders_created", "orders", ["created_at", "id"])


def downgrade() -> None:
    raise RuntimeError("Downgrading would discard fulfillment audit records")
