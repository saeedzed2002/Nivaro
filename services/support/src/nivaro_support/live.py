import asyncio
import logging
from datetime import UTC, datetime
from uuid import UUID

from redis.asyncio import Redis
from redis.exceptions import RedisError
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from nivaro_support.contracts import Actor, History, ReadState
from nivaro_support.conversations import message_history
from nivaro_support.models import MessageOutboxRow, MessageRow, ReadCursorRow
from nivaro_support.settings import Database

CHANNEL = "nivaro.support.message.v1"
PAGE_SIZE = 10
logger = logging.getLogger(__name__)


class NotificationBus:
    def __init__(self) -> None:
        self.subscribers: dict[UUID, set[asyncio.Event]] = {}

    def subscribe(self, conversation: UUID, wake: asyncio.Event) -> None:
        self.subscribers.setdefault(conversation, set()).add(wake)

    def unsubscribe(self, conversation: UUID, wake: asyncio.Event) -> None:
        subscribers = self.subscribers[conversation]
        subscribers.remove(wake)
        if not subscribers:
            del self.subscribers[conversation]

    async def listen(self, redis: Redis) -> None:
        disconnected = False
        while True:
            try:
                async with redis.pubsub() as subscription:
                    await subscription.subscribe(CHANNEL)
                    while True:
                        notification = await subscription.get_message(timeout=1)
                        if notification is None:
                            continue
                        if notification["type"] == "subscribe":
                            # A fresh subscription may follow a gap in Redis delivery.
                            disconnected = False
                            for subscribers in self.subscribers.values():
                                for wake in subscribers:
                                    wake.set()
                        elif notification["type"] == "message":
                            data = notification["data"]
                            if isinstance(data, bytes) and len(data) == 16:
                                for wake in self.subscribers.get(UUID(bytes=data), ()):
                                    wake.set()
            except RedisError:
                if not disconnected:
                    logger.warning("Support live notifications disconnected")
                disconnected = True
                await asyncio.sleep(1)


class ConversationStream:
    def __init__(self, bus: NotificationBus) -> None:
        self.bus = bus
        self.wake = asyncio.Event()
        self.conversation: UUID | None = None
        self.after = 0
        self.receipts = ReadState(own_sequence=0, peer_sequence=0)

    def close(self) -> None:
        if self.conversation is not None:
            self.bus.unsubscribe(self.conversation, self.wake)
            self.conversation = None

    async def subscribe(
        self, db: Database, actor: Actor, conversation: UUID, after: int
    ) -> History:
        replaced = conversation != self.conversation
        if replaced:
            self.bus.subscribe(conversation, self.wake)
        try:
            page = await history(db, actor, conversation, after)
        except BaseException:
            if replaced:
                self.bus.unsubscribe(conversation, self.wake)
            raise
        if replaced:
            self.close()
            self.conversation = conversation
        self.after = min(after, page.conversation.last_sequence)
        self.advance(page)
        self.receipts = page.receipts
        return page

    def advance(self, page: History) -> None:
        if page.messages:
            self.after = page.messages[-1].sequence


async def history(db: Database, actor: Actor, conversation: UUID, after: int) -> History:
    async with db.sessions() as session:
        return await message_history(session, actor, conversation, after, limit=PAGE_SIZE)


async def publish_next(db: Database, redis: Redis) -> bool:
    async with db.sessions() as session, session.begin():
        event = (
            await session.execute(
                select(MessageOutboxRow, MessageRow.conversation_id)
                .join(MessageRow, MessageOutboxRow.message_id == MessageRow.id)
                .where(MessageOutboxRow.published_at.is_(None))
                .order_by(MessageOutboxRow.created_at, MessageOutboxRow.message_id)
                .with_for_update(of=MessageOutboxRow, skip_locked=True)
                .limit(1)
            )
        ).one_or_none()
        if event is None:
            return False
        outbox, conversation = event
        # Redis carries only a wake signal. Replicas retrieve content from PostgreSQL.
        async with asyncio.timeout(1):
            await redis.publish(CHANNEL, conversation.bytes)
        outbox.published_at = datetime.now(UTC)
        return True


async def publish_read_cursor(db: Database, redis: Redis) -> bool:
    async with db.sessions() as session, session.begin():
        row = await session.scalar(
            select(ReadCursorRow)
            .where(ReadCursorRow.published_sequence < ReadCursorRow.sequence)
            .order_by(
                ReadCursorRow.conversation_id, ReadCursorRow.reader_kind, ReadCursorRow.reader_id
            )
            .with_for_update(skip_locked=True)
            .limit(1)
        )
        if row is None:
            return False
        async with asyncio.timeout(1):
            await redis.publish(CHANNEL, row.conversation_id.bytes)
        row.published_sequence = row.sequence
        return True


async def publish_outbox(db: Database, redis: Redis) -> None:
    delayed = False
    while True:
        try:
            published = await publish_next(db, redis)
            receipt_published = await publish_read_cursor(db, redis)
            delayed = False
            if not published and not receipt_published:
                await asyncio.sleep(0.25)
        except (RedisError, SQLAlchemyError, TimeoutError):
            if not delayed:
                logger.warning("Support outbox publication delayed")
            delayed = True
            await asyncio.sleep(1)
