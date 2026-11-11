"""Bounded HTTP catalog projection. No catalog persistence imports or reservations."""

import asyncio
from typing import Annotated, Literal
from uuid import UUID

import httpx
from pydantic import BaseModel, Field, StrictBool, ValidationError

from nivaro_cart.domain.mutations import Market

Money = Annotated[int, Field(strict=True, gt=0, le=9_000_000_000_000)]


class Offer(BaseModel):
    market: Market
    currency: Literal["IRR", "USD"]
    amount_minor: Money
    price_version: Annotated[int, Field(strict=True, gt=0)]
    available_for_sale: StrictBool
    reference_only: StrictBool


class Summary(BaseModel):
    variant_id: UUID
    product_id: UUID
    name: Annotated[str, Field(min_length=1, max_length=4000)]
    slug: Annotated[str, Field(min_length=1, max_length=4000)]
    sku: Annotated[str, Field(min_length=1, max_length=100)]
    image: Annotated[str, Field(max_length=4096)]
    image_kind: Literal["illustration", "exact_sku"]
    available_quantity: Annotated[int, Field(strict=True, ge=0, le=1_000_000)] | None
    offer: Offer | None


class Book(BaseModel):
    market: Market
    currency: Literal["IRR", "USD"]
    items: Annotated[list[Summary], Field(max_length=50)]
    missing_ids: Annotated[list[UUID], Field(max_length=50)]
    reserves_stock: Literal[False]


class CatalogUnavailable(Exception):
    pass


class Catalog:
    def __init__(self, client: httpx.AsyncClient):
        self.client = client

    async def summaries(self, ids: list[UUID], market: Market) -> dict[UUID, Summary | None]:
        unique = list(dict.fromkeys(ids))
        if not unique:
            return {}
        currency = "IRR" if market == "ir" else "USD"
        result: dict[UUID, Summary | None] = {}
        try:
            async with asyncio.timeout(4):
                # The default cart limit fits one request. Larger configured
                # limits use bounded batches under the same overall deadline.
                for offset in range(0, len(unique), 50):
                    batch = unique[offset : offset + 50]
                    async with self.client.stream(
                        "POST",
                        "/api/v1/catalog/variant-summaries",
                        json={
                            "variant_ids": [str(key) for key in batch],
                            "market": market,
                            "currency": currency,
                        },
                    ) as response:
                        if response.status_code != 200:
                            raise CatalogUnavailable
                        data = bytearray()
                        async for chunk in response.aiter_bytes(chunk_size=8192):
                            data.extend(chunk)
                            if len(data) > 1_048_576:
                                raise CatalogUnavailable
                    book = Book.model_validate_json(data)
                    returned = [item.variant_id for item in book.items] + book.missing_ids
                    if (
                        book.market != market
                        or book.currency != currency
                        or len(returned) != len(batch)
                        or set(returned) != set(batch)
                    ):
                        raise CatalogUnavailable
                    for item in book.items:
                        offer = item.offer
                        if offer and (
                            offer.market != market
                            or offer.currency != currency
                            or (currency == "IRR" and offer.amount_minor % 10)
                            or (offer.reference_only and offer.available_for_sale)
                        ):
                            raise CatalogUnavailable
                        result[item.variant_id] = item
                    result.update(dict.fromkeys(book.missing_ids))
            return result
        except (httpx.HTTPError, TimeoutError, ValidationError, ValueError) as exc:
            raise CatalogUnavailable from exc
