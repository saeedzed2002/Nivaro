from typing import Annotated, Literal, Self
from uuid import UUID

from pydantic import Field, model_validator

from nivaro_catalog.domain.contracts import Contract, MarketContext, Offer, Product, Variant


class ProductPage(Contract):
    items: list[Product]
    page: int
    page_size: int
    total: int


class ComparisonRequest(MarketContext):
    variant_ids: Annotated[list[UUID], Field(min_length=2, max_length=2)]

    @model_validator(mode="after")
    def distinct_variants(self) -> Self:
        if len(set(self.variant_ids)) != 2:
            raise ValueError("Select two distinct variants")
        return self


class ComparisonColumn(Contract):
    product_id: UUID
    slug: str
    name: str
    variant: Variant
    offer: Offer | None


class ComparisonRow(Contract):
    key: str
    values: list[str | int | bool | None]
    different: bool


class Comparison(MarketContext):
    category: str
    columns: list[ComparisonColumn]
    rows: list[ComparisonRow]
    declares_winner: Literal[False] = False


class ErrorDetail(Contract):
    code: str
    message: str
    details: list[str] = Field(default_factory=list)
    request_id: str


class ErrorEnvelope(Contract):
    error: ErrorDetail
