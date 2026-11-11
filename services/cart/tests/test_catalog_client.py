import copy
from uuid import uuid4

import httpx
import pytest

from nivaro_cart.infrastructure.catalog import Catalog, CatalogUnavailable


@pytest.mark.parametrize(
    "corruption",
    [
        "market",
        "missing_id",
        "duplicate",
        "money_bool",
        "fractional_toman",
        "stock_negative",
        "oversized",
        "http_error",
    ],
)
async def test_catalog_projection_rejects_untrusted_or_incomplete_response(corruption):
    variant = uuid4()
    item = {
        "variant_id": str(variant),
        "product_id": str(uuid4()),
        "name": "Test",
        "slug": "test",
        "sku": "TEST",
        "image": "/test.webp",
        "image_kind": "illustration",
        "available_quantity": 4,
        "offer": {
            "market": "ir",
            "currency": "IRR",
            "amount_minor": 12340,
            "price_version": 1,
            "available_for_sale": True,
            "reference_only": False,
        },
    }
    body = {
        "market": "ir",
        "currency": "IRR",
        "items": [item],
        "missing_ids": [],
        "reserves_stock": False,
    }
    if corruption == "market":
        item["offer"]["market"], item["offer"]["currency"] = "international", "USD"
    elif corruption == "missing_id":
        body["items"] = []
    elif corruption == "duplicate":
        body["items"].append(copy.deepcopy(item))
    elif corruption == "money_bool":
        item["offer"]["amount_minor"] = True
    elif corruption == "fractional_toman":
        item["offer"]["amount_minor"] = 12341
    elif corruption == "stock_negative":
        item["available_quantity"] = -1

    def transport(request):
        if corruption == "oversized":
            return httpx.Response(200, content=b" " * 1_048_577)
        if corruption == "http_error":
            return httpx.Response(500)
        return httpx.Response(200, json=body)

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(transport), base_url="http://catalog.test"
    ) as client:
        with pytest.raises(CatalogUnavailable):
            await Catalog(client).summaries([variant], "ir")


async def test_second_batch_failure_never_returns_partial_prices():
    ids = [uuid4() for _ in range(51)]
    calls = 0

    def transport(request):
        nonlocal calls
        calls += 1
        if calls == 2:
            return httpx.Response(503)
        return httpx.Response(
            200,
            json={
                "market": "ir",
                "currency": "IRR",
                "items": [],
                "missing_ids": [str(key) for key in ids[:50]],
                "reserves_stock": False,
            },
        )

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(transport), base_url="http://catalog.test"
    ) as client:
        assert await Catalog(client).summaries([], "ir") == {} and calls == 0
        with pytest.raises(CatalogUnavailable):
            await Catalog(client).summaries(ids, "ir")
        assert calls == 2
