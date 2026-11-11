"""Bounded optional cache for validated public projections only."""

import asyncio
import hashlib
import json
from collections.abc import Awaitable, Callable

from pydantic import BaseModel, ValidationError
from redis.asyncio import Redis
from redis.asyncio.retry import Retry
from redis.backoff import NoBackoff
from redis.exceptions import RedisError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from nivaro_catalog.infrastructure.models import PublicCacheGeneration
from nivaro_catalog.settings import Settings


class PublicCache:
    def __init__(self, settings: Settings):
        self.redis: Redis | None = None
        self.retry_after = 0.0
        if settings.cache_host:
            self.redis = Redis(
                host=settings.cache_host,
                password=settings.cache_password_file.read_text().strip(),
                max_connections=12,
                socket_connect_timeout=0.15,
                socket_timeout=0.15,
                retry=Retry(NoBackoff(), 0),
            )

    async def close(self) -> None:
        if self.redis is not None:
            await self.redis.aclose()

    async def read[T: BaseModel](
        self,
        db: AsyncSession,
        model: type[T],
        arguments: tuple[object, ...],
        load: Callable[[], Awaitable[T]],
    ) -> T:
        clock = asyncio.get_running_loop().time
        if self.redis is None or clock() < self.retry_after:
            return await load()
        generation = (
            await db.execute(
                select(PublicCacheGeneration.token).where(PublicCacheGeneration.id == 1)
            )
        ).scalar_one()
        query = json.dumps(arguments, separators=(",", ":"), ensure_ascii=False).encode()
        key = f"catalog:public:v1:{generation.hex}:{model.__name__}:{hashlib.sha256(query).hexdigest()}"
        try:
            async with asyncio.timeout(0.25):
                payload = await self.redis.get(key)
            if payload is not None:
                try:
                    return model.model_validate_json(payload)
                except ValidationError:
                    pass
        except (RedisError, TimeoutError):
            self.retry_after = clock() + 2
            return await load()
        result = await load()
        data = result.model_dump_json().encode()
        if len(data) <= 1024 * 1024:
            try:
                async with asyncio.timeout(0.25):
                    await self.redis.set(key, data, ex=60)
            except (RedisError, TimeoutError):
                self.retry_after = clock() + 2
        return result
