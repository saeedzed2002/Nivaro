from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from nivaro_orders.application.reservations import db_time
from nivaro_orders.infrastructure.models import Order, OrderItem, OutboxEvent


async def record_paid_event(db: AsyncSession, order: Order) -> None:
    items = await db.scalars(
        select(OrderItem).where(OrderItem.order_id == order.id).order_by(OrderItem.source_line_id)
    )
    event_id = uuid4()
    now = await db_time(db)
    db.add(
        OutboxEvent(
            id=event_id,
            order_id=order.id,
            available_at=now,
            envelope={
                "event_id": str(event_id),
                "event_type": "order.paid",
                "schema_version": 1,
                "producer": "orders",
                "occurred_at": now.isoformat(),
                "aggregate_id": str(order.id),
                "aggregate_version": order.version,
                "correlation_id": str(order.id),
                "causation_id": None,
                "payload": {
                    "cart_id": str(order.cart_id),
                    "cart_version": order.cart_version,
                    "customer_id": str(order.customer_id),
                    "allocation_id": str(order.id),
                    "market": order.market,
                    "currency": order.currency,
                    "lines": [
                        {
                            "id": str(item.source_line_id),
                            "version": item.source_line_version,
                            "group_id": str(item.source_group_id) if item.source_group_id else None,
                            "quantity": item.quantity,
                        }
                        for item in items
                    ],
                },
            },
        )
    )
