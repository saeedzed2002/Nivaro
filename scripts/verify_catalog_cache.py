"""Run only inside the helper's disposable catalog container."""
import asyncio
import os
import statistics
import sys
import time

import httpx
from sqlalchemy import select, update

from nivaro_catalog.api.schemas import ProductPage
from nivaro_catalog.domain.contracts import Product
from nivaro_catalog.infrastructure import repository
from nivaro_catalog.infrastructure.database import Database
from nivaro_catalog.infrastructure.models import OfferRow, ProductRow, PublicCacheGeneration, VariantRow
from nivaro_catalog.infrastructure.public_cache import PublicCache
from nivaro_catalog.settings import Settings


async def main():
    assert os.environ.get("NIVARO_CACHE_QA") == "disposable"
    settings = Settings()
    database = Database(settings)
    cache = PublicCache(settings)
    mode = sys.argv[1]
    try:
        if mode == "normal":
            calls = 0

            async def read():
                async with database.sessions() as db:
                    async def load():
                        nonlocal calls
                        calls += 1
                        result = await repository.product(db, "amd-ryzen-7-9800x3d")
                        assert result is not None
                        return result
                    return await cache.read(db, Product, ("qa-detail",), load)

            first = await read()
            assert (await read()) == first and calls == 1
            async with database.sessions() as db:
                generation = await db.scalar(select(PublicCacheGeneration.token))
                await db.execute(update(ProductRow).where(ProductRow.id == first.id).values(name="Rollback probe"))
                await db.rollback()
                assert await db.scalar(select(PublicCacheGeneration.token)) == generation
            assert await read() == first and calls == 1

            loaded, release = asyncio.Event(), asyncio.Event()
            async def stale_reader():
                async with database.sessions() as db:
                    async def slow_load():
                        loaded.set()
                        await release.wait()
                        return first
                    return await cache.read(db, Product, ("race",), slow_load)
            stale = asyncio.create_task(stale_reader())
            await loaded.wait()
            async with database.sessions() as db, db.begin():
                await db.execute(update(ProductRow).where(ProductRow.id == first.id).values(name="Committed cache probe"))
            release.set()
            await stale
            async with database.sessions() as db:
                async def current():
                    result = await repository.product(db, "amd-ryzen-7-9800x3d")
                    assert result is not None
                    return result
                fresh = await cache.read(db, Product, ("race",), current)
                assert fresh.name == "Committed cache probe"
            assert (await read()).name == "Committed cache probe"
            async with database.sessions() as db, db.begin():
                await db.execute(update(ProductRow).where(ProductRow.id == first.id).values(name=first.name))
            assert (await read()).name == first.name
            variant = next(v for v in first.variants if v.offers)
            async with database.sessions() as db, db.begin():
                await db.execute(update(VariantRow).where(VariantRow.id == variant.id).values(on_hand=variant.on_hand + 2))
                await db.execute(update(OfferRow).where(OfferRow.variant_id == variant.id).values(amount_minor=OfferRow.amount_minor + 10, price_version=OfferRow.price_version + 1))
            changed = await read()
            updated_variant = next(v for v in changed.variants if v.id == variant.id)
            assert updated_variant.on_hand == variant.on_hand + 2
            assert {o.market: o.amount_minor for o in updated_variant.offers} == {o.market: o.amount_minor + 10 for o in variant.offers}
            async with database.sessions() as db, db.begin():
                await db.execute(update(VariantRow).where(VariantRow.id == variant.id).values(on_hand=variant.on_hand))
                await db.execute(update(OfferRow).where(OfferRow.variant_id == variant.id).values(amount_minor=OfferRow.amount_minor - 10, price_version=OfferRow.price_version + 1))
            restored = next(v for v in (await read()).variants if v.id == variant.id)
            assert restored.on_hand == variant.on_hand
            assert {o.market: o.amount_minor for o in restored.offers} == {o.market: o.amount_minor for o in variant.offers}
            assert cache.redis is not None
            keys = [key async for key in cache.redis.scan_iter(match="catalog:public:v1:*")]
            assert keys and all([0 < await cache.redis.ttl(key) <= 60 for key in keys])
            print("Cache hit, committed invalidation, rollback and late-writer race passed.")
        async with httpx.AsyncClient(base_url="http://127.0.0.1:8000", timeout=5) as client:
            for market in ("ir", "international"):
                response = await client.get("/api/v1/catalog/products", params={"market": market})
                assert response.status_code == 200, response.text
                ProductPage.model_validate(response.json())
            for endpoint in ("/api/v1/catalog/products?market=ir", "/api/v1/catalog/products/amd-ryzen-7-9800x3d"):
                timings = []
                for _ in range(21):
                    start = time.perf_counter()
                    result = await client.get(endpoint)
                    assert result.status_code == 200, result.text
                    timings.append(1000 * (time.perf_counter() - start))
                values = sorted(timings[1:])
                print(f"{mode} {endpoint}: median={statistics.median(values):.2f}ms p95={values[18]:.2f}ms")
            # Private admin responses must remain unauthorized with a warm public cache.
            assert (await client.get("/api/v1/admin/catalog/products")).status_code == 401
        if mode == "outage":
            assert cache.redis is not None
            try:
                await cache.redis.ping()
            except Exception:
                print("Cache outage confirmed; public API and authorization checks passed.")
            else:
                raise AssertionError("Expected cache outage")
    finally:
        await cache.close()
        await database.engine.dispose()


asyncio.run(main())
