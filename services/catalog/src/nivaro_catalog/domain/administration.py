"""Explicit staff commands; readiness, counters and revisions are never client writable."""

from typing import Annotated, Literal, Self
from uuid import UUID

from pydantic import Field, StrictBool, StringConstraints, model_validator

from nivaro_catalog.domain.contracts import (
    Contract,
    Evidence,
    Localized,
    MarketContext,
    MoneyAmount,
    Specifications,
)

Version = Annotated[int, Field(strict=True, ge=1, le=2_000_000_000)]
Slug = Annotated[str, StringConstraints(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$", max_length=160)]
ShortText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=240)]
Reason = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)]
Stock = Annotated[int, Field(strict=True, ge=0, le=1_000_000)]


class ProductContent(Contract):
    slug: Slug
    name: ShortText
    description: Localized
    category_id: UUID
    brand: Annotated[str, StringConstraints(strip_whitespace=True, max_length=120)] = ""
    highlights: list[ShortText] = Field(default_factory=list, max_length=20)

    @model_validator(mode="after")
    def translated_content(self) -> Self:
        if not self.description.fa.strip() or not self.description.en.strip():
            raise ValueError("Both descriptions must contain text")
        return self


class ProductEdit(ProductContent):
    expected_version: Version


class CategoryContent(Contract):
    slug: Annotated[str, StringConstraints(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$", max_length=80)]
    name: Localized
    parent_id: UUID | None = None

    @model_validator(mode="after")
    def meaningful_names(self) -> Self:
        if any(
            not value.strip() or len(value.strip()) > 120 for value in (self.name.fa, self.name.en)
        ):
            raise ValueError("Category names must contain 1 to 120 characters")
        return self


class CategoryEdit(CategoryContent):
    expected_version: Version


class StatusChange(Contract):
    expected_version: Version
    status: Literal["draft", "published", "archived"]


class VariantContent(Contract):
    expected_version: Version
    sku: Annotated[str, StringConstraints(pattern=r"^[A-Z0-9][A-Z0-9._-]*$", max_length=100)]
    packaging: Localized
    specifications: Specifications
    evidence: list[Evidence] = Field(default_factory=list, max_length=20)

    @model_validator(mode="after")
    def nonempty_packaging(self) -> Self:
        if not self.packaging.fa.strip() or not self.packaging.en.strip():
            raise ValueError("Both packaging descriptions must contain text")
        return self


class StockChange(Contract):
    expected_version: Version
    expected_stock_version: Version
    on_hand: Stock
    stock_verified: StrictBool
    reason: Reason


class OfferChange(MarketContext):
    expected_version: Version
    # Zero means create only; a missing offer never silently replaces a known revision.
    expected_price_version: Annotated[int, Field(strict=True, ge=0, le=2_000_000_000)]
    amount_minor: MoneyAmount
    available_for_sale: StrictBool
    reference_only: StrictBool
    source: Evidence
    seller: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]
    reason: Reason

    @model_validator(mode="after")
    def valid_offer(self) -> Self:
        if self.currency == "IRR" and self.amount_minor % 10:
            raise ValueError("IRR amounts must be multiples of ten rials")
        if self.reference_only and self.available_for_sale:
            raise ValueError("Research references cannot be offered for sale")
        return self


class AdministrationError(Exception):
    def __init__(self, code: str, message: str, status: int = 409) -> None:
        self.code, self.message, self.status = code, message, status
        super().__init__(message)
