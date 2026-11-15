import hashlib
from datetime import UTC
from typing import Annotated, Literal, Self
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import func, or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from nivaro_catalog.infrastructure.models import DeliveredOrderRow, PurchaseEntitlementRow

DELIVERED_QUEUE = "catalog.order.delivered.v1"


class DeliveredProducts(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    customer_id: UUID
    product_ids: Annotated[
        list[UUID], Field(min_length=1, max_length=100, json_schema_extra={"uniqueItems": True})
    ]


class OrderDelivered(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    event_id: UUID
    event_type: Literal["order.delivered"]
    schema_version: Literal[1]
    producer: Literal["orders"]
    occurred_at: AwareDatetime
    aggregate_id: UUID
    aggregate_version: Annotated[int, Field(strict=True, ge=1, le=2147483647)]
    correlation_id: UUID
    causation_id: UUID | None
    payload: DeliveredProducts

    @model_validator(mode="after")
    def check_identity(self) -> Self:
        if self.correlation_id != self.aggregate_id:
            raise ValueError("The correlation must identify the delivered order")
        if len(set(self.payload.product_ids)) != len(self.payload.product_ids):
            raise ValueError("Purchased product IDs must be unique")
        return self


class DeliveryConflict(Exception):
    """A known event ID or order ID was reused with different evidence."""


async def record_purchase_entitlements(db: AsyncSession, event: OrderDelivered) -> None:
    product_ids = sorted(event.payload.product_ids)
    occurred_at = event.occurred_at.astimezone(UTC)
    normalized = event.model_copy(
        update={
            "occurred_at": occurred_at,
            "payload": event.payload.model_copy(update={"product_ids": product_ids}),
        }
    )
    fingerprint = hashlib.sha256(normalized.model_dump_json().encode()).hexdigest()
    async with db.begin():
        accepted = await db.scalar(
            insert(DeliveredOrderRow)
            .values(event_id=event.event_id, order_id=event.aggregate_id, fingerprint=fingerprint)
            .on_conflict_do_nothing()
            .returning(DeliveredOrderRow.event_id)
        )
        if accepted is None:
            prior = (
                await db.scalars(
                    select(DeliveredOrderRow).where(
                        or_(
                            DeliveredOrderRow.event_id == event.event_id,
                            DeliveredOrderRow.order_id == event.aggregate_id,
                        )
                    )
                )
            ).all()
            if len(prior) == 1 and prior[0].fingerprint == fingerprint:
                return
            raise DeliveryConflict()

        # Stable product order keeps concurrent grants for the same buyer from locking in reverse.
        grant = insert(PurchaseEntitlementRow).values(
            [
                {
                    "customer_id": event.payload.customer_id,
                    "product_id": product_id,
                    "first_delivered_at": occurred_at,
                }
                for product_id in product_ids
            ]
        )
        await db.execute(
            grant.on_conflict_do_update(
                index_elements=[
                    PurchaseEntitlementRow.customer_id,
                    PurchaseEntitlementRow.product_id,
                ],
                set_={
                    "first_delivered_at": func.least(
                        PurchaseEntitlementRow.first_delivered_at, grant.excluded.first_delivered_at
                    )
                },
            )
        )
