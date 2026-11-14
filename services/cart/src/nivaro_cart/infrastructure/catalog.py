"""Bounded HTTP catalog projection. No catalog persistence imports or reservations."""

import asyncio
import hashlib
import json
from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

import httpx
from pydantic import BaseModel, Field, StrictBool, ValidationError

from nivaro_cart.domain.mutations import Market

Money = Annotated[int, Field(strict=True, gt=0, le=9_000_000_000_000)]
BuildMode = Literal["complete_build", "parts_only"]
Compatibility = Literal["compatible", "incompatible", "incomplete", "needs_review"]
Digest = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]


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


class SelectionUnavailable(Exception):
    """Catalog rejected a missing variant or a variant assigned to the wrong slot."""


class Localized(BaseModel):
    fa: str
    en: str


class Finding(BaseModel):
    code: str
    status: Compatibility
    slots: list[str]
    message: Localized
    corrective_action: Localized


class Evaluation(BaseModel):
    market: Market
    currency: Literal["IRR", "USD"]
    mode: BuildMode
    selection_hash: Digest
    spec_versions: dict[UUID, Annotated[int, Field(strict=True, gt=0)]]
    ruleset_version: Annotated[str, Field(min_length=1, max_length=80)]
    status: Compatibility
    findings: list[Finding]
    evaluated_at: datetime
    estimated_power_w: int | None
    power_method: str
    reserves_stock: Literal[False]


class Catalog:
    def __init__(self, client: httpx.AsyncClient):
        self.client = client

    async def _fetch(
        self, path: str, body: dict[str, object], *, evaluates_build: bool = False
    ) -> bytearray:
        async with self.client.stream("POST", path, json=body) as response:
            if evaluates_build and response.status_code == 422:
                raise SelectionUnavailable
            if response.status_code != 200:
                raise CatalogUnavailable
            data = bytearray()
            async for chunk in response.aiter_bytes(chunk_size=8192):
                data.extend(chunk)
                if len(data) > 1_048_576:
                    raise CatalogUnavailable
            return data

    async def evaluate(
        self,
        *,
        market: Market,
        mode: BuildMode,
        dedicated_gpu: bool,
        selections: list[tuple[str, UUID, int]],
    ) -> Evaluation:
        currency = "IRR" if market == "ir" else "USD"
        normalized = [
            {
                "slot_key": slot,
                "role": slot.split(":", 1)[0],
                "variant_id": str(key),
                "quantity": quantity,
            }
            for slot, key, quantity in sorted(selections)
        ]
        body: dict[str, object] = {
            "market": market,
            "currency": currency,
            "mode": mode,
            "requires_dedicated_gpu": dedicated_gpu,
            "selections": normalized,
        }
        expected_hash = hashlib.sha256(
            json.dumps(body, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        try:
            async with asyncio.timeout(4):
                data = await self._fetch(
                    "/api/v1/catalog/build-evaluations", body, evaluates_build=True
                )
            result = Evaluation.model_validate_json(data)
        except (httpx.HTTPError, TimeoutError, ValidationError, ValueError) as exc:
            raise CatalogUnavailable from exc
        if (
            result.market != market
            or result.currency != currency
            or result.mode != mode
            or result.selection_hash != expected_hash
            or set(result.spec_versions) != {key for _, key, _ in selections}
        ):
            raise CatalogUnavailable
        return result

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
                    data = await self._fetch(
                        "/api/v1/catalog/variant-summaries",
                        {
                            "variant_ids": [str(key) for key in batch],
                            "market": market,
                            "currency": currency,
                        },
                    )
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
