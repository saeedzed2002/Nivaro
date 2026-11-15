from typing import Annotated, Literal
from uuid import UUID

from pydantic import Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from nivaro_orders.application.order_history import OrderSnapshot, StateChange, read_snapshot
from nivaro_orders.application.reservations import record_order_transition
from nivaro_orders.domain.checkout import CheckoutError, Contract, OrderState, Version
from nivaro_orders.infrastructure.models import Order, OrderTransition

type Action = Literal["prepare", "ship", "deliver"]
FLOW: dict[Action, tuple[OrderState, OrderState]] = {
    "prepare": ("paid", "processing"),
    "ship": ("processing", "shipped"),
    "deliver": ("shipped", "delivered"),
}


class Prepare(Contract):
    action: Literal["prepare"]
    expected_version: Version


class Ship(Contract):
    action: Literal["ship"]
    expected_version: Version
    tracking_reference: Annotated[str, Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._ -]{0,79}$")]


class Deliver(Contract):
    action: Literal["deliver"]
    expected_version: Version


FulfillmentCommand = Annotated[Prepare | Ship | Deliver, Field(discriminator="action")]


class StaffTransition(StateChange):
    reason: str
    staff_actor_id: UUID | None


class FulfillmentView(Contract):
    id: UUID
    status: OrderState
    version: Version
    tracking_reference: str | None
    allowed_actions: list[Action]
    timeline: list[StaffTransition]


class FulfillmentDetails(FulfillmentView):
    snapshot: OrderSnapshot


async def fulfillment_view(db: AsyncSession, order: Order) -> FulfillmentView:
    changes = await db.scalars(
        select(OrderTransition)
        .where(OrderTransition.order_id == order.id)
        .order_by(OrderTransition.version)
    )
    return FulfillmentView.model_validate(
        {
            "id": order.id,
            "status": order.status,
            "version": order.version,
            "tracking_reference": order.tracking_reference,
            "allowed_actions": [
                action for action, (source, _) in FLOW.items() if source == order.status
            ],
            "timeline": [
                StaffTransition.model_validate(change, from_attributes=True) for change in changes
            ],
        }
    )


async def read_fulfillment(db: AsyncSession, order_id: UUID) -> FulfillmentDetails:
    order = await db.scalar(select(Order).where(Order.id == order_id).with_for_update(read=True))
    if order is None:
        raise CheckoutError("checkout.not_found")
    view = await fulfillment_view(db, order)
    return FulfillmentDetails(**view.model_dump(), snapshot=await read_snapshot(db, order))


async def change_fulfillment(
    db: AsyncSession, order_id: UUID, actor_id: UUID, command: FulfillmentCommand
) -> FulfillmentView:
    async with db.begin():
        order = await db.get(Order, order_id, with_for_update=True)
        if order is None:
            raise CheckoutError("checkout.not_found")
        source, target = FLOW[command.action]
        reason = f"fulfillment.{command.action}"
        if order.version != command.expected_version:
            prior = await db.get(OrderTransition, (order.id, command.expected_version + 1))
            if (
                prior is None
                or (prior.status, prior.reason, prior.staff_actor_id) != (target, reason, actor_id)
                or (
                    isinstance(command, Ship)
                    and order.tracking_reference != command.tracking_reference
                )
            ):
                raise CheckoutError("orders.version_conflict")
            return await fulfillment_view(db, order)
        if order.status != source:
            raise CheckoutError("orders.invalid_transition")
        if isinstance(command, Ship):
            order.tracking_reference = command.tracking_reference
        record_order_transition(db, order, target, reason, staff_actor_id=actor_id)
        await db.flush()
        return await fulfillment_view(db, order)
