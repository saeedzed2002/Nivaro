import asyncio
import logging
from collections.abc import Awaitable, Callable

import aio_pika
from aio_pika.abc import AbstractIncomingMessage
from aio_pika.exceptions import AMQPException, ChannelInvalidStateError

from nivaro_orders.infrastructure.database import Database
from nivaro_orders.settings import Settings

log = logging.getLogger(__name__)


async def subscribe(
    queue_name: str,
    consume: Callable[[AbstractIncomingMessage, Database], Awaitable[None]],
) -> None:
    settings = Settings()
    secret = settings.event_broker_password_file.read_text(encoding="utf-8").strip()
    if len(secret) < 32:
        raise ValueError("Orders event credential is missing or invalid")
    database = Database(settings)
    try:
        while True:
            try:
                # Open a new iterator and subscription after each disconnect.
                async with await aio_pika.connect(
                    host=settings.event_broker_host,
                    login="nivaro_orders_events",
                    password=secret,
                    virtualhost="commerce-events",
                    heartbeat=15,
                    timeout=5,
                ) as connection:
                    async with connection.channel() as channel:
                        await channel.set_qos(prefetch_count=4)
                        queue = await channel.get_queue(queue_name, ensure=False)
                        async with queue.iterator() as messages:
                            async for message in messages:
                                await consume(message, database)
            except (AMQPException, ChannelInvalidStateError, OSError, TimeoutError):
                log.warning("Orders event broker is unavailable queue=%s", queue_name)
            await asyncio.sleep(2)
    finally:
        await database.engine.dispose()
