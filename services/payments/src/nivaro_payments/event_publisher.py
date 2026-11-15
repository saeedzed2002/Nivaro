import asyncio
import json
import logging
from dataclasses import dataclass
from datetime import timedelta
from typing import Any
from uuid import UUID, uuid4

import aio_pika
from aio_pika.abc import AbstractExchange
from aio_pika.exceptions import AMQPException, ChannelInvalidStateError
from pamqp.commands import Basic
from sqlalchemy import func, or_, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from nivaro_payments.attempts import database_time
from nivaro_payments.models import OutboxEvent
from nivaro_payments.settings import Database, Settings

EVENT_EXCHANGE = "nivaro.events"
ATTEMPT_LIMIT = 8
log = logging.getLogger(__name__)


@dataclass(frozen=True)
class Delivery:
    id: UUID
    lease_id: UUID
    routing_key: str
    envelope: dict[str, Any]


async def claim(db: AsyncSession) -> Delivery | None:
    async with db.begin():
        row = await db.scalar(
            select(OutboxEvent)
            .where(
                OutboxEvent.published_at.is_(None),
                OutboxEvent.failed_at.is_(None),
                OutboxEvent.available_at <= func.statement_timestamp(),
                or_(
                    OutboxEvent.lease_until.is_(None),
                    OutboxEvent.lease_until <= func.statement_timestamp(),
                ),
            )
            .order_by(OutboxEvent.available_at, OutboxEvent.id)
            .limit(1)
            .with_for_update(skip_locked=True)
        )
        if row is None:
            return None
        now = await database_time(db)
        if row.attempts >= ATTEMPT_LIMIT:
            row.failed_at = now
            row.last_error = "publish.unconfirmed"
            row.lease_id = row.lease_until = None
            log.error("Outbox event exhausted confirmation attempts event_id=%s", row.id)
            return None
        lease = uuid4()
        row.attempts += 1
        row.lease_id, row.lease_until = lease, now + timedelta(seconds=30)
        return Delivery(row.id, lease, row.event_type, row.envelope)


async def finish(db: AsyncSession, delivery: Delivery, *, confirmed: bool) -> None:
    async with db.begin():
        row = await db.get(OutboxEvent, delivery.id, with_for_update=True, populate_existing=True)
        if row is None or row.lease_id != delivery.lease_id:
            return
        row.lease_id = row.lease_until = None
        now = await database_time(db)
        if confirmed:
            row.published_at = now
            row.last_error = None
        else:
            row.last_error = "publish.unconfirmed"
            if row.attempts >= ATTEMPT_LIMIT:
                row.failed_at = now
                log.error("Outbox event exhausted confirmation attempts event_id=%s", row.id)
            else:
                row.available_at = now + timedelta(seconds=min(60, 2**row.attempts))


async def publish_one(database: Database, exchange: AbstractExchange) -> bool:
    async with database.sessions() as db:
        delivery = await claim(db)
    if delivery is None:
        return False
    confirmed = False
    try:
        async with asyncio.timeout(5):
            result = await exchange.publish(
                aio_pika.Message(
                    body=json.dumps(delivery.envelope, separators=(",", ":")).encode(),
                    message_id=str(delivery.id),
                    content_type="application/json",
                    delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
                ),
                routing_key=delivery.routing_key,
                mandatory=True,
            )
            confirmed = isinstance(result, Basic.Ack)
    except (AMQPException, ChannelInvalidStateError, OSError, TimeoutError):
        pass
    async with database.sessions() as db:
        await finish(db, delivery, confirmed=confirmed)
    return True


async def run() -> None:
    settings = Settings()
    secret = settings.event_broker_password_file.read_text(encoding="utf-8").strip()
    if len(secret) < 32:
        raise ValueError("Payments event credential is missing or invalid")
    database = Database(settings)
    try:
        while True:
            try:
                async with await aio_pika.connect(
                    host=settings.event_broker_host,
                    login="nivaro_payments_events",
                    password=secret,
                    virtualhost="commerce-events",
                    heartbeat=15,
                    timeout=5,
                ) as connection:
                    async with connection.channel(
                        publisher_confirms=True, on_return_raises=True
                    ) as channel:
                        exchange = await channel.get_exchange(EVENT_EXCHANGE, ensure=False)
                        while not channel.is_closed:
                            try:
                                if not await publish_one(database, exchange):
                                    await asyncio.sleep(1)
                            except SQLAlchemyError:
                                log.exception("Payments outbox database operation failed")
                                await asyncio.sleep(2)
            except (AMQPException, ChannelInvalidStateError, OSError, TimeoutError):
                log.warning("Payments event broker is unavailable")
            await asyncio.sleep(2)
    finally:
        await database.engine.dispose()


if __name__ == "__main__":
    asyncio.run(run())
