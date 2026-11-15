import asyncio
from dataclasses import dataclass
from time import time
from typing import Literal
from uuid import UUID, uuid4

from redis.asyncio import Redis
from redis.exceptions import RedisError

from nivaro_support.contracts import Actor, Kind
from nivaro_support.conversations import require_conversation
from nivaro_support.live import CHANNEL
from nivaro_support.settings import Database

Signal = Literal["presence", "typing"]
TTL_MS: dict[Signal, int] = {"presence": 24_000, "typing": 5_000}


@dataclass(frozen=True)
class Participant:
    kind: Kind
    user_id: UUID


def key(conversation: UUID, person: Participant, signal: Signal) -> str:
    return f"nivaro:support:activity:{conversation}:{person.kind}:{person.user_id}:{signal}"


def now_ms() -> int:
    return int(time() * 1000)


async def participants(
    db: Database, actor: Actor, conversation: UUID
) -> tuple[Participant | None, Participant | None]:
    async with db.sessions() as session, session.begin():
        row = await require_conversation(session, actor, conversation, reading=True)
        if row.status == "closed":
            return None, None
        if actor.kind == "customer":
            peer = Participant("admin", row.assigned_agent_id) if row.assigned_agent_id else None
            return Participant("customer", actor.user_id), peer
        if row.assigned_agent_id == actor.user_id:
            return Participant("admin", actor.user_id), Participant("customer", row.customer_id)
        return None, None


class ActivitySession:
    def __init__(self, redis: Redis) -> None:
        self.redis = redis
        self.member = uuid4().hex
        self.current: tuple[UUID, Participant] | None = None
        self.last_sent: dict[Signal, int] = {}

    async def update(
        self, db: Database, actor: Actor, conversation: UUID, signal: Signal, active: bool
    ) -> None:
        own, _ = await participants(db, actor, conversation)
        if own is None:
            return
        self.current = (conversation, own)
        name = key(conversation, own, signal)
        current = now_ms()
        ttl = TTL_MS[signal]
        try:
            async with asyncio.timeout(0.8), self.redis.pipeline() as pipe:
                if active:
                    pipe.zremrangebyscore(name, "-inf", current)
                    pipe.zadd(name, {self.member: current + ttl})
                    pipe.pexpire(name, ttl)
                else:
                    pipe.zrem(name, self.member)
                pipe.publish(CHANNEL, conversation.bytes)
                await pipe.execute()
        except (RedisError, TimeoutError):
            # A stale indicator expires even if Redis is unreachable.
            return

    async def changes(
        self, db: Database, actor: Actor, conversation: UUID
    ) -> list[tuple[Signal, int]]:
        if not self.current or self.current[0] != conversation:
            return []
        _, peer = await participants(db, actor, conversation)
        expires: dict[Signal, int] = dict.fromkeys(TTL_MS, 0)
        if peer is not None:
            try:
                async with asyncio.timeout(0.8), self.redis.pipeline(transaction=False) as pipe:
                    for signal in TTL_MS:
                        pipe.zrange(key(conversation, peer, signal), -1, -1, withscores=True)
                    rows = await pipe.execute()
                current = now_ms()
                for signal, entries in zip(TTL_MS, rows, strict=True):
                    if entries and entries[0][1] > current:
                        expires[signal] = int(entries[0][1])
            except (RedisError, TimeoutError):
                pass
        changes = []
        current = now_ms()
        for signal, deadline in expires.items():
            if self.last_sent.get(signal, 0) != deadline:
                self.last_sent[signal] = deadline
                changes.append((signal, min(TTL_MS[signal], max(0, deadline - current))))
        return changes

    async def leave(self) -> None:
        current, self.current = self.current, None
        self.last_sent.clear()
        if current is None:
            return
        conversation, own = current
        try:
            async with asyncio.timeout(0.8), self.redis.pipeline() as pipe:
                for signal in TTL_MS:
                    pipe.zrem(key(conversation, own, signal), self.member)
                pipe.publish(CHANNEL, conversation.bytes)
                await pipe.execute()
        except (RedisError, TimeoutError):
            return
