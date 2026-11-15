"""Publish new and previously paid orders for version-safe cart cleanup."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0009_order_paid_outbox"
down_revision = "0008_payment_initiations"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "event_outbox",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "order_id",
            sa.Uuid(),
            sa.ForeignKey("orders.id", ondelete="RESTRICT"),
            nullable=False,
            unique=True,
        ),
        sa.Column("available_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("envelope", JSONB(), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("lease_id", sa.Uuid()),
        sa.Column("lease_until", sa.DateTime(timezone=True)),
        sa.Column("published_at", sa.DateTime(timezone=True)),
        sa.Column("failed_at", sa.DateTime(timezone=True)),
        sa.Column("last_error", sa.String(80)),
        sa.CheckConstraint(
            "attempts >= 0 AND (lease_id IS NULL) = (lease_until IS NULL) AND (published_at IS NULL OR failed_at IS NULL)",
            name="orders_outbox_delivery",
        ),
    )
    op.create_index(
        "ix_orders_outbox_due",
        "event_outbox",
        ["available_at", "id"],
        postgresql_where=sa.text("published_at IS NULL AND failed_at IS NULL"),
    )
    op.execute("""
        WITH paid AS MATERIALIZED (
            SELECT DISTINCT ON (order_id) order_id, version, occurred_at, gen_random_uuid() AS event_id
            FROM order_transitions WHERE status = 'paid' ORDER BY order_id, version
        )
        INSERT INTO event_outbox (id, order_id, available_at, envelope)
        SELECT p.event_id, o.id, now(), jsonb_build_object(
            'event_id', p.event_id, 'event_type', 'order.paid', 'schema_version', 1,
            'producer', 'orders', 'occurred_at', p.occurred_at, 'aggregate_id', o.id,
            'aggregate_version', p.version, 'correlation_id', o.id, 'causation_id', null,
            'payload', jsonb_build_object('cart_id', o.cart_id, 'cart_version', o.cart_version,
                'customer_id', o.customer_id, 'allocation_id', o.id, 'market', o.market,
                'currency', o.currency, 'lines', (
                    SELECT jsonb_agg(jsonb_build_object('id', i.source_line_id,
                        'version', i.source_line_version, 'group_id', i.source_group_id,
                        'quantity', i.quantity) ORDER BY i.source_line_id)
                    FROM order_items i WHERE i.order_id = o.id)))
        FROM paid p JOIN orders o ON o.id = p.order_id
    """)


def downgrade() -> None:
    raise RuntimeError("Downgrading would discard paid order events")
