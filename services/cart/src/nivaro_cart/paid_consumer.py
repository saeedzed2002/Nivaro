import asyncio
import logging

import aio_pika
from aio_pika.abc import AbstractIncomingMessage
from aio_pika.exceptions import AMQPException, ChannelInvalidStateError
from pydantic import ValidationError
from sqlalchemy.exc import SQLAlchemyError

from nivaro_cart.domain.paid_cleanup import (
    PAID_QUEUE,
    CleanupRejected,
    OrderPaid,
    apply_paid_cleanup,
)
from nivaro_cart.infrastructure.database import Database
from nivaro_cart.settings import Settings

log = logging.getLogger(__name__)


async def consume(message: AbstractIncomingMessage, database: Database) -> None:
    try:
        if message.content_type != "application/json" or len(message.body) > 32768:
            await message.reject(requeue=False)
            return
        event = OrderPaid.model_validate_json(message.body)
        if (message.message_id, message.routing_key) != (str(event.event_id), event.event_type):
            await message.reject(requeue=False)
            return
        async with database.sessions() as db:
            await apply_paid_cleanup(db, event)
    except (ValidationError, CleanupRejected):
        log.warning("Rejected invalid paid cart cleanup message")
        await message.reject(requeue=False)
        return
    except SQLAlchemyError:
        count = message.headers.get("x-delivery-count", 0)
        attempt = min(max(count, 0), 4) if type(count) is int else 0
        log.warning("Cart cleanup transaction will be retried event_id=%s", event.event_id)
        await asyncio.sleep(min(10, 2**attempt))
        await message.nack(requeue=True)
        return
    await message.ack()


async def run() -> None:
    settings = Settings()
    secret = settings.event_broker_password_file.read_text(encoding="utf-8").strip()
    if len(secret) < 32:
        raise ValueError("Cart event credential is missing or invalid")
    database = Database(settings)
    try:
        while True:
            try:
                async with await aio_pika.connect(
                    host=settings.event_broker_host,
                    login="nivaro_cart_events",
                    password=secret,
                    virtualhost="commerce-events",
                    heartbeat=15,
                    timeout=5,
                ) as connection:
                    async with connection.channel() as channel:
                        await channel.set_qos(prefetch_count=4)
                        queue = await channel.get_queue(PAID_QUEUE, ensure=False)
                        async with queue.iterator() as messages:
                            async for message in messages:
                                await consume(message, database)
            except (AMQPException, ChannelInvalidStateError, OSError, TimeoutError):
                log.warning("Cart event broker is unavailable")
            await asyncio.sleep(2)
    finally:
        await database.engine.dispose()


if __name__ == "__main__":
    asyncio.run(run())
