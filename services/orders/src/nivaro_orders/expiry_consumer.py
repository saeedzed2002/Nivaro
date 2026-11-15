import asyncio
import logging

from aio_pika.abc import AbstractIncomingMessage
from pydantic import ValidationError
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from nivaro_orders.application.reservations import transition
from nivaro_orders.domain.events import EXPIRED_RESERVATION_QUEUE, ExpiredReservation
from nivaro_orders.event_subscription import subscribe
from nivaro_orders.infrastructure.database import Database
from nivaro_orders.infrastructure.models import InboxEvent, Order

log = logging.getLogger(__name__)


async def apply_expiry(db: AsyncSession, event: ExpiredReservation) -> None:
    async with db.begin():
        inserted = await db.scalar(
            insert(InboxEvent)
            .values(
                consumer_name=EXPIRED_RESERVATION_QUEUE,
                event_id=event.event_id,
                aggregate_id=event.aggregate_id,
                aggregate_version=event.aggregate_version,
            )
            .on_conflict_do_nothing()
            .returning(InboxEvent.event_id)
        )
        if inserted is None:
            return
        order = await db.get(
            Order, event.aggregate_id, with_for_update=True, populate_existing=True
        )
        payload = event.payload
        if (
            order is not None
            and order.status in {"pending_reservation", "awaiting_payment"}
            and (order.quote_id, order.market, order.currency)
            == (payload.quote_id, payload.market, payload.currency)
            and (
                order.reservation_expires_at is None
                or payload.expires_at >= order.reservation_expires_at
            )
        ):
            await transition(db, order, "expired", "reservation.expired", payload.expires_at)


async def consume(message: AbstractIncomingMessage, database: Database) -> None:
    try:
        if message.content_type != "application/json" or len(message.body) > 16384:
            await message.reject(requeue=False)
            return
        event = ExpiredReservation.model_validate_json(message.body)
        if message.message_id != str(event.event_id):
            await message.reject(requeue=False)
            return
    except ValidationError:
        log.warning("Rejected malformed reservation expiry event")
        await message.reject(requeue=False)
        return
    try:
        async with database.sessions() as db:
            await apply_expiry(db, event)
    except SQLAlchemyError:
        count = message.headers.get("x-delivery-count", 0)
        attempt = min(max(count, 0), 4) if type(count) is int else 0
        log.warning("Expiry transaction will be retried event_id=%s", event.event_id)
        await asyncio.sleep(min(10, 2**attempt))
        await message.nack(requeue=True)
        return
    await message.ack()


if __name__ == "__main__":
    asyncio.run(subscribe(EXPIRED_RESERVATION_QUEUE, consume))
