"""Run the read-only catalog benchmark inside the disposable cache verifier."""

import asyncio
import json
import math
import os
import statistics
import sys
from hashlib import sha256
from time import perf_counter

import httpx

from nivaro_catalog.api.schemas import ProductPage

ENDPOINT = "/api/v1/catalog/products"
ROUNDS = 20
QUERIES: tuple[tuple[str, dict[str, str | int]], ...] = (
    ("first", {"q": "loadprobe"}),
    ("deep", {"q": "loadprobe", "page": 30}),
    ("english", {"q": "loadprobe amd"}),
    ("persian", {"q": "loadprobe پردازنده", "category": "cpu"}),
    ("irr", {"q": "loadprobe", "market": "ir", "sort": "price_asc", "min_price": 1_000_000}),
    (
        "usd",
        {"q": "loadprobe", "market": "international", "sort": "price_asc", "max_price": 250_000},
    ),
)


async def main() -> None:
    assert os.environ.get("NIVARO_CACHE_QA") == "disposable"
    async with httpx.AsyncClient(base_url="http://127.0.0.1:8000", timeout=10) as client:
        baselines: dict[str, ProductPage] = {}
        for name, params in QUERIES:
            response = await client.get(ENDPOINT, params=params)
            response.raise_for_status()
            result = ProductPage.model_validate(response.json())
            assert result.items and all(item.slug.startswith("load-") for item in result.items)
            assert result.page == params.get("page", 1)
            if name in ("irr", "usd"):
                prices = [
                    min(
                        offer.amount_minor
                        for variant in product.variants
                        for offer in variant.offers
                        if offer.market == params["market"]
                    )
                    for product in result.items
                ]
                assert prices == sorted(prices)
                minimum = int(params.get("min_price", 0))
                maximum = int(params.get("max_price", 9_000_000_000_000))
                assert all(minimum <= price <= maximum for price in prices)
            baselines[name] = result

        first = baselines["first"]
        assert first.total >= 1_000
        assert baselines["deep"].total == first.total
        assert not (
            {item.id for item in first.items} & {item.id for item in baselines["deep"].items}
        )
        assert baselines["irr"].total != baselines["usd"].total

        async def request(name: str, params: dict[str, str | int]) -> float:
            started = perf_counter()
            response = await client.get(ENDPOINT, params=params)
            elapsed_ms = (perf_counter() - started) * 1_000
            response.raise_for_status()
            assert ProductPage.model_validate(response.json()) == baselines[name], name
            return elapsed_ms

        durations = []
        for _ in range(ROUNDS):
            durations.extend(
                await asyncio.gather(*(request(name, params) for name, params in QUERIES))
            )
        durations.sort()
        payload = json.dumps(
            {name: result.model_dump(mode="json") for name, result in baselines.items()},
            sort_keys=True,
        )
        print(
            json.dumps(
                {
                    "mode": sys.argv[1],
                    "fixture_products": first.total,
                    "requests": len(durations),
                    "concurrency": len(QUERIES),
                    "median_ms": round(statistics.median(durations), 2),
                    "p95_ms": round(durations[math.ceil(len(durations) * 0.95) - 1], 2),
                    "payload_sha256": sha256(payload.encode()).hexdigest(),
                }
            )
        )


asyncio.run(main())
