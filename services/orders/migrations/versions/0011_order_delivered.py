"""Queue a verified-purchase event for each completed delivery."""

import sqlalchemy as sa
from alembic import op

revision = "0011_order_delivered"
down_revision = "0010_order_fulfillment"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("event_outbox", sa.Column("event_type", sa.String(32)))
    op.execute("UPDATE event_outbox SET event_type = 'order.paid'")
    op.alter_column("event_outbox", "event_type", nullable=False)
    op.drop_constraint("event_outbox_order_id_key", "event_outbox", type_="unique")
    op.create_unique_constraint(
        "uq_orders_outbox_order_event", "event_outbox", ["order_id", "event_type"]
    )
    op.create_check_constraint(
        "orders_outbox_event_type",
        "event_outbox",
        "event_type IN ('order.paid','order.delivered') AND (envelope->>'event_type') IS NOT DISTINCT FROM event_type",
    )
    op.execute("""
        WITH delivered AS MATERIALIZED (
            SELECT DISTINCT ON (order_id) order_id, version, occurred_at, gen_random_uuid() AS event_id
            FROM order_transitions WHERE status = 'delivered' ORDER BY order_id, version
        )
        INSERT INTO event_outbox (id, order_id, event_type, available_at, envelope)
        SELECT d.event_id, o.id, 'order.delivered', now(), jsonb_build_object(
            'event_id', d.event_id, 'event_type', 'order.delivered', 'schema_version', 1,
            'producer', 'orders', 'occurred_at', d.occurred_at, 'aggregate_id', o.id,
            'aggregate_version', d.version, 'correlation_id', o.id, 'causation_id', null,
            'payload', jsonb_build_object('customer_id', o.customer_id, 'product_ids', (
                SELECT jsonb_agg(DISTINCT i.product_id ORDER BY i.product_id)
                FROM order_items i WHERE i.order_id = o.id)))
        FROM delivered d JOIN orders o ON o.id = d.order_id
    """)


def downgrade() -> None:
    raise RuntimeError("Downgrading would discard delivery events")
