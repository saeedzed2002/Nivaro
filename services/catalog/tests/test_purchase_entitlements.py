import asyncio
import os
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy import select

from nivaro_catalog.domain.purchase_entitlements import (
    DeliveredProducts,
    DeliveryConflict,
    OrderDelivered,
    record_purchase_entitlements,
)
from nivaro_catalog.infrastructure.database import Database
from nivaro_catalog.infrastructure.models import DeliveredOrderRow, PurchaseEntitlementRow
from nivaro_catalog.settings import Settings


def delivery() -> OrderDelivered:
    order_id = uuid4()
    return OrderDelivered(
        event_id=uuid4(),
        event_type="order.delivered",
        schema_version=1,
        producer="orders",
        occurred_at=datetime.now(UTC),
        aggregate_id=order_id,
        aggregate_version=7,
        correlation_id=order_id,
        causation_id=None,
        payload=DeliveredProducts(customer_id=uuid4(), product_ids=[uuid4(), uuid4()]),
    )


def test_delivery_contract_rejects_mismatched_order_and_duplicate_products():
    data = delivery().model_dump(mode="json")
    with pytest.raises(ValidationError, match="correlation"):
        OrderDelivered.model_validate({**data, "correlation_id": str(uuid4())})
    duplicate = data["payload"]["product_ids"][0]
    data["payload"]["product_ids"] = [duplicate, duplicate]
    with pytest.raises(ValidationError, match="unique"):
        OrderDelivered.model_validate(data)


@pytest.mark.skipif(
    not os.getenv("CATALOG_DB_HOST") or os.getenv("CATALOG_DISPOSABLE_TESTS") != "1",
    reason="Dedicated disposable catalog database required",
)
async def test_entitlements_deduplicate_delivery_and_keep_earliest_evidence():
    event = delivery()
    order_id = uuid4()
    earlier = event.model_copy(
        update={
            "event_id": uuid4(),
            "aggregate_id": order_id,
            "correlation_id": order_id,
            "occurred_at": event.occurred_at - timedelta(days=1),
            "payload": event.payload.model_copy(
                update={"product_ids": event.payload.product_ids[:1]}
            ),
        }
    )
    database = Database(Settings())

    async def consume(delivery_event):
        async with database.sessions() as db:
            await record_purchase_entitlements(db, delivery_event)

    try:
        await asyncio.gather(*(consume(event) for _ in range(6)), consume(earlier))
        with pytest.raises(DeliveryConflict):
            await consume(event.model_copy(update={"event_id": uuid4()}))
        with pytest.raises(DeliveryConflict):
            await consume(
                event.model_copy(
                    update={"payload": event.payload.model_copy(update={"customer_id": uuid4()})}
                )
            )
        async with database.sessions() as db:
            processed = await db.scalars(
                select(DeliveredOrderRow.event_id).where(
                    DeliveredOrderRow.order_id.in_([event.aggregate_id, order_id])
                )
            )
            assert set(processed) == {event.event_id, earlier.event_id}
            entitlements = await db.scalars(
                select(PurchaseEntitlementRow).where(
                    PurchaseEntitlementRow.customer_id == event.payload.customer_id
                )
            )
            first, second = event.payload.product_ids
            assert {row.product_id: row.first_delivered_at for row in entitlements} == {
                first: earlier.occurred_at,
                second: event.occurred_at,
            }
    finally:
        await database.engine.dispose()
