from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Query, Request
from pydantic import AwareDatetime
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from nivaro_orders.api.checkout import ErrorResponse
from nivaro_orders.api.fulfillment import staff_actor
from nivaro_orders.application.checkout_flow import CheckoutFlow
from nivaro_orders.domain.checkout import Contract, Market, MarketTerms, OrderState
from nivaro_orders.infrastructure.models import Order, OrderPaymentAttempt, OrderPaymentCompensation
from nivaro_orders.infrastructure.simulator_payments import (
    AttemptStatus,
    OperationsAttempt,
    OperationsPage,
    SimulatorPayments,
)

router = APIRouter(
    prefix="/api/v1/admin/payments",
    tags=["staff payments"],
    responses={status: {"model": ErrorResponse} for status in (401, 403, 404, 422, 503)},
)


class CompensationView(Contract):
    refund_id: UUID
    captured_minor: int
    closes_order: bool
    reason: str
    state: Literal["pending", "awaiting_evidence", "completed", "manual_review"]
    retry_at: AwareDatetime | None
    last_error: str | None


class PaymentOrderView(MarketTerms):
    status: OrderState
    total_minor: int
    reservation_error: str | None
    recorded_outcome: str | None
    disposition: str | None
    compensation: CompensationView | None


class OperationsDetails(Contract):
    attempt: OperationsAttempt
    order: PaymentOrderView | None


async def order_context(db: AsyncSession, attempt: OperationsAttempt) -> PaymentOrderView | None:
    result = await db.execute(
        select(Order, OrderPaymentAttempt, OrderPaymentCompensation)
        .outerjoin(
            OrderPaymentAttempt,
            and_(OrderPaymentAttempt.id == attempt.id, OrderPaymentAttempt.order_id == Order.id),
        )
        .outerjoin(
            OrderPaymentCompensation, OrderPaymentCompensation.attempt_id == OrderPaymentAttempt.id
        )
        .where(Order.id == attempt.order_id)
    )
    row = result.one_or_none()
    if row is None:
        return None
    order, recorded, compensation = row
    return PaymentOrderView.model_validate(
        {
            "market": order.market,
            "currency": order.currency,
            "status": order.status,
            "total_minor": order.total_minor,
            "reservation_error": order.reservation_error,
            "recorded_outcome": recorded.outcome if recorded is not None else None,
            "disposition": recorded.disposition if recorded is not None else None,
            "compensation": (
                CompensationView.model_validate(compensation, from_attributes=True)
                if compensation is not None
                else None
            ),
        }
    )


@router.get("/attempts", operation_id="listStaffPaymentAttempts")
async def list_attempts(
    request: Request,
    status: AttemptStatus | None = None,
    market: Market | None = None,
    order_id: UUID | None = None,
    before: UUID | None = None,
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
) -> OperationsPage:
    flow: CheckoutFlow = request.app.state.checkout
    await staff_actor(request, flow, mutating=False, area="payments")
    payments: SimulatorPayments = request.app.state.payment_attempts
    return await payments.list_operations(status, market, order_id, before, limit)


@router.get("/attempts/{attempt_id}", operation_id="readStaffPaymentAttempt")
async def read_attempt(request: Request, attempt_id: UUID) -> OperationsDetails:
    flow: CheckoutFlow = request.app.state.checkout
    await staff_actor(request, flow, mutating=False, area="payments")
    payments: SimulatorPayments = request.app.state.payment_attempts
    attempt = await payments.read_operation(attempt_id)
    async with flow.database.sessions() as db:
        return OperationsDetails(attempt=attempt, order=await order_context(db, attempt))
