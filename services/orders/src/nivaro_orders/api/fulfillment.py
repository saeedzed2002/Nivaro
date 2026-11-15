from datetime import UTC, date, datetime, time, timedelta
from typing import Annotated
from uuid import UUID
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Query, Request
from pydantic import Field

from nivaro_orders.api.checkout import ErrorResponse, mutation_context
from nivaro_orders.application.checkout_flow import CheckoutFlow
from nivaro_orders.application.fulfillment import (
    FulfillmentCommand,
    FulfillmentDetails,
    FulfillmentView,
    change_fulfillment,
    read_fulfillment,
)
from nivaro_orders.application.order_history import OrderHistory, list_orders
from nivaro_orders.domain.checkout import Market, OrderState
from nivaro_orders.infrastructure.checkout_sources import SourceError, StaffArea

router = APIRouter(
    prefix="/api/v1/admin/orders",
    tags=["staff orders"],
    responses={status: {"model": ErrorResponse} for status in (401, 403, 404, 409, 422, 503)},
)
TEHRAN = ZoneInfo("Asia/Tehran")
PlacementDate = Annotated[date, Field(ge=date(1900, 1, 1), le=date(9998, 12, 31))]


def placement_boundary(day: date) -> datetime:
    return datetime.combine(day, time.min, TEHRAN).astimezone(UTC)


async def staff_actor(
    request: Request, flow: CheckoutFlow, *, mutating: bool, area: StaffArea = "orders"
) -> UUID:
    access = request.cookies.get("nivaro_admin_access", "")
    if not access or len(access) > 8192:
        raise SourceError("session.invalid", 401)
    return (
        await flow.sources.staff(access, mutation_context(request) if mutating else None, area=area)
    ).actor_id


@router.get("/history", operation_id="listStaffOrders")
async def history(
    request: Request,
    before: UUID | None = None,
    status: OrderState | None = None,
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
    market: Market | None = None,
    order_id: UUID | None = None,
    placed_from: Annotated[
        PlacementDate | None, Query(description="First day in Asia/Tehran")
    ] = None,
    placed_through: Annotated[
        PlacementDate | None, Query(description="Last day in Asia/Tehran")
    ] = None,
) -> OrderHistory:
    flow: CheckoutFlow = request.app.state.checkout
    await staff_actor(request, flow, mutating=False)
    if placed_from is not None and placed_through is not None and placed_from > placed_through:
        raise SourceError("orders.invalid_date_range", 422)
    async with flow.database.sessions() as db:
        return await list_orders(
            db,
            None,
            before,
            limit,
            status=status,
            market=market,
            order_id=order_id,
            placed_from=placement_boundary(placed_from) if placed_from is not None else None,
            placed_before=(
                placement_boundary(placed_through + timedelta(days=1))
                if placed_through is not None
                else None
            ),
        )


@router.get("/{order_id}/fulfillment", operation_id="readOrderFulfillment")
async def read(request: Request, order_id: UUID) -> FulfillmentDetails:
    flow: CheckoutFlow = request.app.state.checkout
    await staff_actor(request, flow, mutating=False)
    async with flow.database.sessions() as db:
        return await read_fulfillment(db, order_id)


@router.post("/{order_id}/fulfillment", operation_id="changeOrderFulfillment")
async def change(request: Request, order_id: UUID, command: FulfillmentCommand) -> FulfillmentView:
    flow: CheckoutFlow = request.app.state.checkout
    actor_id = await staff_actor(request, flow, mutating=True)
    async with flow.database.sessions() as db:
        return await change_fulfillment(db, order_id, actor_id, command)
