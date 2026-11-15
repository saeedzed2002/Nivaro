from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from nivaro_orders.application.reservations import db_time
from nivaro_orders.infrastructure.models import Order, OrderItem, OutboxEvent


async def record_delivered_event(db: AsyncSession, order: Order) -> None:
    product_ids = await db.scalars(
        select(OrderItem.product_id)
        .where(OrderItem.order_id == order.id)
        .distinct()
        .order_by(OrderItem.product_id)
    )
    occurred_at = await db_time(db)
    event_id = uuid4()
    db.add(
        OutboxEvent(
            id=event_id,
            order_id=order.id,
            event_type="order.delivered",
            available_at=occurred_at,
            envelope={
                "event_id": str(event_id),
                "event_type": "order.delivered",
                "schema_version": 1,
                "producer": "orders",
                "occurred_at": occurred_at.isoformat(),
                "aggregate_id": str(order.id),
                "aggregate_version": order.version,
                "correlation_id": str(order.id),
                "causation_id": None,
                "payload": {
                    "customer_id": str(order.customer_id),
                    "product_ids": [str(product_id) for product_id in product_ids],
                },
            },
        )
    )
