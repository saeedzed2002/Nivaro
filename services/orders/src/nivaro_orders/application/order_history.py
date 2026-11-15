from collections import defaultdict
from typing import Literal
from uuid import UUID

from pydantic import AwareDatetime
from sqlalchemy import select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession

from nivaro_orders.domain.checkout import (
    AddressSnapshot,
    CheckoutError,
    Contract,
    MarketTerms,
    OrderState,
    Totals,
)
from nivaro_orders.infrastructure.models import (
    Order,
    OrderAddress,
    OrderConfiguration,
    OrderItem,
    OrderTransition,
)


class HistoryEntry(MarketTerms):
    id: UUID
    created_at: AwareDatetime
    status: OrderState
    total_minor: int


class OrderHistory(Contract):
    orders: list[HistoryEntry]
    next_before: UUID | None


class PurchasedItem(Contract):
    source_line_id: UUID
    slot_key: str | None
    sku: str
    name: str
    quantity: int
    unit_price_minor: int


class PurchasedGroup(Contract):
    id: UUID
    name: str
    mode: Literal["complete_build", "parts_only"]
    items: list[PurchasedItem]


class StateChange(Contract):
    version: int
    status: OrderState
    occurred_at: AwareDatetime


class DeliveryAddress(Contract):
    recipient: str
    street: str
    city: str
    country: str
    postal_code: str


class OrderDetails(HistoryEntry):
    totals: Totals
    address: DeliveryAddress
    standalone: list[PurchasedItem]
    groups: list[PurchasedGroup]
    timeline: list[StateChange]
    tracking_reference: str | None = None


async def list_orders(
    db: AsyncSession,
    customer_id: UUID | None,
    before: UUID | None,
    limit: int,
    *,
    status: OrderState | None = None,
) -> OrderHistory:
    owned = select(Order)
    if customer_id is not None:
        owned = owned.where(Order.customer_id == customer_id)
    query = owned.order_by(Order.created_at.desc(), Order.id.desc()).limit(limit + 1)
    if status is not None:
        query = query.where(Order.status == status)
    if before is not None:
        boundary = await db.scalar(owned.where(Order.id == before))
        if boundary is None:
            raise CheckoutError("checkout.not_found")
        query = query.where(
            tuple_(Order.created_at, Order.id) < tuple_(boundary.created_at, boundary.id)
        )
    rows = (await db.scalars(query)).all()
    return OrderHistory(
        orders=[HistoryEntry.model_validate(row, from_attributes=True) for row in rows[:limit]],
        next_before=rows[limit - 1].id if len(rows) > limit else None,
    )


async def read_details(db: AsyncSession, customer_id: UUID, order_id: UUID) -> OrderDetails:
    # Order writers lock the parent before changing its status or adding a transition.
    order = await db.scalar(
        select(Order)
        .where(Order.id == order_id, Order.customer_id == customer_id)
        .with_for_update(read=True)
    )
    if order is None:
        raise CheckoutError("checkout.not_found")
    saved_address = await db.get(OrderAddress, order.id)
    assert saved_address is not None
    address = AddressSnapshot.model_validate(saved_address.snapshot)
    items = await db.scalars(
        select(OrderItem)
        .where(OrderItem.order_id == order.id)
        .order_by(OrderItem.slot_key, OrderItem.source_line_id)
    )
    by_group: dict[UUID | None, list[PurchasedItem]] = defaultdict(list)
    for item in items:
        by_group[item.source_group_id].append(
            PurchasedItem.model_validate(item, from_attributes=True)
        )
    groups = await db.scalars(
        select(OrderConfiguration)
        .where(OrderConfiguration.order_id == order.id)
        .order_by(OrderConfiguration.source_group_id)
    )
    changes = await db.scalars(
        select(OrderTransition)
        .where(OrderTransition.order_id == order.id)
        .order_by(OrderTransition.version)
    )
    return OrderDetails(
        **HistoryEntry.model_validate(order, from_attributes=True).model_dump(),
        totals=Totals.model_validate(order, from_attributes=True),
        tracking_reference=order.tracking_reference,
        address=DeliveryAddress.model_validate(address, from_attributes=True),
        standalone=by_group[None],
        groups=[
            PurchasedGroup(
                id=group.source_group_id,
                name=group.snapshot["name"],
                mode=group.snapshot["mode"],
                items=by_group[group.source_group_id],
            )
            for group in groups
        ],
        timeline=[StateChange.model_validate(change, from_attributes=True) for change in changes],
    )
