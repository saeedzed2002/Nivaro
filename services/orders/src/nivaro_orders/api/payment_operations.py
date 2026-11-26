from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Header, Query, Request
from pydantic import AwareDatetime
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from nivaro_orders.api.checkout import ErrorResponse
from nivaro_orders.api.fulfillment import staff_actor
from nivaro_orders.application.checkout_flow import CheckoutFlow
from nivaro_orders.application.refund_history import (
    CompensationState,
    RefundFilter,
    RefundQueue,
    list_refunds,
)
from nivaro_orders.application.refund_retries import (
    RefundRetryView,
    RetryRefundCommand,
    retry_refund,
)
from nivaro_orders.domain.checkout import Contract, Market, MarketTerms, OrderState
from nivaro_orders.infrastructure.models import (
    Order,
    OrderPaymentAttempt,
    OrderPaymentCompensation,
    OrderRefundRetry,
)
from nivaro_orders.infrastructure.simulator_payments import (
    AttemptStatus,
    OperationsAttempt,
    OperationsPage,
    ReconciliationView,
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
    state: CompensationState
    retry_at: AwareDatetime | None
    last_error: str | None
    attempts: int


class PaymentOrderView(MarketTerms):
    status: OrderState
    total_minor: int
    reservation_error: str | None
    recorded_outcome: str | None
    disposition: str | None
    compensation: CompensationView | None
    last_refund_retry: RefundRetryView | None


class OperationsDetails(Contract):
    attempt: OperationsAttempt
    order: PaymentOrderView | None
    last_reconciliation: ReconciliationView | None


class RefundQueueCount(Contract):
    manual_review: int


async def order_context(db: AsyncSession, attempt: OperationsAttempt) -> PaymentOrderView | None:
    latest_retry = (
        select(OrderRefundRetry.operation_id)
        .where(OrderRefundRetry.refund_id == OrderPaymentCompensation.refund_id)
        .order_by(OrderRefundRetry.queued_at.desc(), OrderRefundRetry.operation_id.desc())
        .limit(1)
        .correlate(OrderPaymentCompensation)
        .scalar_subquery()
    )
    result = await db.execute(
        select(Order, OrderPaymentAttempt, OrderPaymentCompensation, OrderRefundRetry)
        .outerjoin(
            OrderPaymentAttempt,
            and_(OrderPaymentAttempt.id == attempt.id, OrderPaymentAttempt.order_id == Order.id),
        )
        .outerjoin(
            OrderPaymentCompensation, OrderPaymentCompensation.attempt_id == OrderPaymentAttempt.id
        )
        .outerjoin(
            OrderRefundRetry,
            and_(
                OrderRefundRetry.refund_id == OrderPaymentCompensation.refund_id,
                OrderRefundRetry.operation_id == latest_retry,
            ),
        )
        .where(Order.id == attempt.order_id)
    )
    row = result.one_or_none()
    if row is None:
        return None
    order, recorded, compensation, retry = row
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
            "last_refund_retry": RefundRetryView.model_validate(retry, from_attributes=True)
            if retry is not None
            else None,
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


@router.get("/refunds", operation_id="listStaffRefunds")
async def refund_queue(
    request: Request,
    state: RefundFilter = "open",
    market: Market | None = None,
    order_id: UUID | None = None,
    before: UUID | None = None,
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
) -> RefundQueue:
    flow: CheckoutFlow = request.app.state.checkout
    await staff_actor(request, flow, mutating=False, area="payments")
    async with flow.database.sessions() as db:
        return await list_refunds(
            db, state=state, market=market, order_id=order_id, before=before, limit=limit
        )


@router.get("/refund-overview", operation_id="readStaffRefundOverview")
async def refund_overview(request: Request) -> RefundQueueCount:
    flow: CheckoutFlow = request.app.state.checkout
    await staff_actor(request, flow, mutating=False, area="payments")
    async with flow.database.sessions() as db:
        count = await db.scalar(
            select(func.count())
            .select_from(OrderPaymentCompensation)
            .where(OrderPaymentCompensation.state == "manual_review")
        )
    return RefundQueueCount(manual_review=count or 0)


@router.get("/attempts/{attempt_id}", operation_id="readStaffPaymentAttempt")
async def read_attempt(request: Request, attempt_id: UUID) -> OperationsDetails:
    flow: CheckoutFlow = request.app.state.checkout
    await staff_actor(request, flow, mutating=False, area="payments")
    payments: SimulatorPayments = request.app.state.payment_attempts
    attempt = await payments.read_operation(attempt_id)
    async with flow.database.sessions() as db:
        return OperationsDetails(
            attempt=attempt,
            order=await order_context(db, attempt),
            last_reconciliation=attempt.last_reconciliation,
        )


@router.post(
    "/attempts/{attempt_id}/reconcile",
    operation_id="reconcileStaffPaymentAttempt",
    responses={409: {"model": ErrorResponse}},
)
async def reconcile_attempt(
    request: Request,
    attempt_id: UUID,
    operation_id: Annotated[UUID, Header(alias="Idempotency-Key")],
) -> ReconciliationView:
    flow: CheckoutFlow = request.app.state.checkout
    actor_id = await staff_actor(request, flow, mutating=True, area="payment_reconciliation")
    payments: SimulatorPayments = request.app.state.payment_attempts
    return await payments.reconcile_operation(attempt_id, operation_id, actor_id)


@router.post(
    "/refunds/{refund_id}/retry",
    operation_id="retryStaffPaymentRefund",
    responses={409: {"model": ErrorResponse}},
)
async def retry_payment_refund(
    request: Request,
    refund_id: UUID,
    body: RetryRefundCommand,
    operation_id: Annotated[UUID, Header(alias="Idempotency-Key")],
) -> RefundRetryView:
    flow: CheckoutFlow = request.app.state.checkout
    actor_id = await staff_actor(request, flow, mutating=True, area="payment_refund")
    async with flow.database.sessions() as db:
        return await retry_refund(db, refund_id, operation_id, actor_id, body)
