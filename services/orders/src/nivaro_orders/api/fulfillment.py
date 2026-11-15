from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query, Request

from nivaro_orders.api.checkout import ErrorResponse, mutation_context
from nivaro_orders.application.checkout_flow import CheckoutFlow
from nivaro_orders.application.fulfillment import (
    FulfillmentCommand,
    FulfillmentView,
    change_fulfillment,
    read_fulfillment,
)
from nivaro_orders.application.order_history import OrderHistory, list_orders
from nivaro_orders.domain.checkout import OrderState
from nivaro_orders.infrastructure.checkout_sources import SourceError

router = APIRouter(
    prefix="/api/v1/admin/orders",
    tags=["staff orders"],
    responses={status: {"model": ErrorResponse} for status in (401, 403, 404, 409, 422, 503)},
)


async def staff_actor(request: Request, flow: CheckoutFlow, *, mutating: bool) -> UUID:
    access = request.cookies.get("nivaro_admin_access", "")
    if not access or len(access) > 8192:
        raise SourceError("session.invalid", 401)
    return (
        await flow.sources.staff(access, mutation_context(request) if mutating else None)
    ).actor_id


@router.get("/history", operation_id="listStaffOrders")
async def history(
    request: Request,
    before: UUID | None = None,
    status: OrderState | None = None,
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
) -> OrderHistory:
    flow: CheckoutFlow = request.app.state.checkout
    await staff_actor(request, flow, mutating=False)
    async with flow.database.sessions() as db:
        return await list_orders(db, None, before, limit, status=status)


@router.get("/{order_id}/fulfillment", operation_id="readOrderFulfillment")
async def read(request: Request, order_id: UUID) -> FulfillmentView:
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
