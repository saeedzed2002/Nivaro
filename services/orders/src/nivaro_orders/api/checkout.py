from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Header, Query, Request

from nivaro_orders.application.checkout_flow import (
    CheckoutFlow,
    ConfirmPreview,
    OrderStatus,
    PreviewResponse,
)
from nivaro_orders.application.order_history import (
    OrderDetails,
    OrderHistory,
    list_orders,
    read_details,
)
from nivaro_orders.application.payment_initiation import StartPayment, request_payment
from nivaro_orders.domain.checkout import CheckoutIntent, Contract
from nivaro_orders.infrastructure.checkout_sources import CustomerContext, SourceError


class ErrorDetail(Contract):
    code: str
    request_id: str


class ErrorResponse(Contract):
    error: ErrorDetail


router = APIRouter(
    prefix="/api/v1/orders",
    tags=["orders"],
    responses={status: {"model": ErrorResponse} for status in (401, 403, 404, 409, 422, 503)},
)


def mutation_context(request: Request) -> dict[str, str]:
    origin = request.headers.get("origin", "")
    csrf = request.headers.get("x-csrf-token", "")
    if not origin or len(origin) > 256 or request.headers.get("sec-fetch-site") == "cross-site":
        raise SourceError("origin.forbidden", 403)
    if not csrf or len(csrf) > 128:
        raise SourceError("csrf.invalid", 403)
    return {"origin": origin, "csrf_token": csrf}


async def actor(request: Request, flow: CheckoutFlow, *, mutating: bool) -> CustomerContext:
    access = request.cookies.get("nivaro_customer_access", "")
    if not access or len(access) > 8192:
        raise SourceError("session.invalid", 401)
    return await flow.sources.customer(access, mutation_context(request) if mutating else None)


@router.post("/checkout/preview", operation_id="previewCheckout")
async def preview(
    request: Request,
    intent: CheckoutIntent,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=1, max_length=128)],
) -> PreviewResponse:
    flow: CheckoutFlow = request.app.state.checkout
    return await flow.preview(await actor(request, flow, mutating=True), idempotency_key, intent)


@router.post("/checkout/{operation_id}/confirm", operation_id="confirmCheckout")
async def confirm(request: Request, operation_id: UUID, body: ConfirmPreview) -> OrderStatus:
    flow: CheckoutFlow = request.app.state.checkout
    return await flow.confirm(
        await actor(request, flow, mutating=True), operation_id, body.confirmation
    )


@router.get("/history", operation_id="listCustomerOrders")
async def history(
    request: Request,
    before: UUID | None = None,
    limit: Annotated[int, Query(ge=1, le=50)] = 12,
) -> OrderHistory:
    flow: CheckoutFlow = request.app.state.checkout
    context = await actor(request, flow, mutating=False)
    async with flow.database.sessions() as db:
        return await list_orders(db, context.customer_id, before, limit)


@router.get("/{order_id}/details", operation_id="readCustomerOrderDetails")
async def details(request: Request, order_id: UUID) -> OrderDetails:
    flow: CheckoutFlow = request.app.state.checkout
    context = await actor(request, flow, mutating=False)
    async with flow.database.sessions() as db:
        return await read_details(db, context.customer_id, order_id)


@router.get("/{order_id}", operation_id="readOrderStatus")
async def order_status(request: Request, order_id: UUID) -> OrderStatus:
    flow: CheckoutFlow = request.app.state.checkout
    context = await actor(request, flow, mutating=False)
    return await flow.status(context.customer_id, order_id)


@router.post("/{order_id}/payment", status_code=202, operation_id="startSimulatedPayment")
async def start_simulated_payment(
    request: Request,
    order_id: UUID,
    body: StartPayment,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=1, max_length=128)],
) -> OrderStatus:
    flow: CheckoutFlow = request.app.state.checkout
    context = await actor(request, flow, mutating=True)
    async with flow.database.sessions() as db:
        await request_payment(
            db, context.customer_id, order_id, body.order_version, idempotency_key
        )
    return await flow.status(context.customer_id, order_id)
