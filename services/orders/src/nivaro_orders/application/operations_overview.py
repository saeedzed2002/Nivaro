from datetime import datetime
from typing import Literal

from pydantic import AwareDatetime
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from nivaro_orders.domain.checkout import Contract, MarketTerms
from nivaro_orders.infrastructure.models import (
    Order,
    OrderPaymentAttempt,
    OrderPaymentRefund,
    OrderTransition,
)


class SalesTotals(MarketTerms):
    paid_orders: int
    gross_minor: str
    confirmed_refund_minor: str
    net_minor: str


class OrderOverview(Contract):
    paid_from: AwareDatetime
    paid_before: AwareDatetime
    sales: list[SalesTotals]
    paid: int
    processing: int
    shipped: int
    payment_review: int


async def order_overview(db: AsyncSession, start: datetime, end: datetime) -> OrderOverview:
    paid = (
        select(OrderTransition.order_id)
        .where(
            OrderTransition.order_id == Order.id,
            OrderTransition.status == "paid",
            OrderTransition.occurred_at >= start,
            OrderTransition.occurred_at < end,
        )
        .exists()
    )
    # Match only the capture that funded fulfillment. Refunds of other attempts never reduce sales.
    recognized = (
        select(
            Order.market,
            Order.currency,
            OrderPaymentAttempt.id.label("payment_id"),
            Order.total_minor,
        )
        .join(OrderPaymentAttempt, OrderPaymentAttempt.order_id == Order.id)
        .where(
            paid,
            OrderPaymentAttempt.disposition == "selected",
            OrderPaymentAttempt.outcome == "payment.succeeded",
            OrderPaymentAttempt.captured_minor == Order.total_minor,
        )
        .cte("recognized_sales")
    )
    receipts = (
        select(
            OrderPaymentRefund.payment_attempt_id.label("payment_id"),
            func.sum(OrderPaymentRefund.amount_minor).label("amount"),
        )
        .join(recognized, recognized.c.payment_id == OrderPaymentRefund.payment_attempt_id)
        .where(OrderPaymentRefund.completed_at < end)
        .group_by(OrderPaymentRefund.payment_attempt_id)
        .subquery()
    )
    grouped = await db.execute(
        select(
            recognized.c.market,
            recognized.c.currency,
            func.count(),
            func.sum(recognized.c.total_minor),
            func.coalesce(func.sum(receipts.c.amount), 0),
        )
        .outerjoin(receipts, receipts.c.payment_id == recognized.c.payment_id)
        .group_by(recognized.c.market, recognized.c.currency)
    )
    totals = {
        (market, currency): (count, gross, refunded)
        for market, currency, count, gross, refunded in grouped
    }
    markets: tuple[
        tuple[Literal["ir"], Literal["IRR"]], tuple[Literal["international"], Literal["USD"]]
    ] = (("ir", "IRR"), ("international", "USD"))
    sales = []
    for market, currency in markets:
        count, gross, refunded = totals.get((market, currency), (0, 0, 0))
        sales.append(
            SalesTotals(
                market=market,
                currency=currency,
                paid_orders=count,
                gross_minor=str(int(gross)),
                confirmed_refund_minor=str(int(refunded)),
                net_minor=str(int(gross - refunded)),
            )
        )

    states = await db.execute(
        select(Order.status, func.count())
        .where(Order.status.in_(("paid", "processing", "shipped", "payment_review")))
        .group_by(Order.status)
    )
    counts = {state: count for state, count in states}
    return OrderOverview(
        paid_from=start,
        paid_before=end,
        sales=sales,
        paid=counts.get("paid", 0),
        processing=counts.get("processing", 0),
        shipped=counts.get("shipped", 0),
        payment_review=counts.get("payment_review", 0),
    )
