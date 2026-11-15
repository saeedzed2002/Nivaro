from typing import Annotated, Literal, Self
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, JsonValue, model_validator

type Market = Literal["ir", "international"]
type Currency = Literal["IRR", "USD"]
Version = Annotated[int, Field(strict=True, ge=1, le=2_147_483_647)]
Amount = Annotated[int, Field(strict=True, ge=0, le=9_000_000_000_000_000)]
Digest = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
CouponCode = Annotated[str, Field(pattern=r"^[A-Z0-9][A-Z0-9_-]{0,39}$")]
Country = Annotated[str, Field(pattern=r"^[A-Z]{2}$")]


class CheckoutError(Exception):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class MarketTerms(Contract):
    market: Market
    currency: Currency

    @model_validator(mode="after")
    def validate_currency(self) -> Self:
        if self.currency != ("IRR" if self.market == "ir" else "USD"):
            raise ValueError("Currency must match the independent market price book")
        return self


class CheckoutIntent(MarketTerms):
    cart_version: Version
    address_id: UUID
    address_version: Version
    coupon_code: CouponCode | None = None


class AddressSnapshot(Contract):
    id: UUID
    version: Version
    label: Annotated[str, Field(max_length=40)]
    recipient: Annotated[str, Field(min_length=1, max_length=80)]
    country: Country
    city: Annotated[str, Field(min_length=1, max_length=80)]
    postal_code: Annotated[str, Field(max_length=20)]
    street: Annotated[str, Field(min_length=1, max_length=500)]
    phone: Annotated[str, Field(pattern=r"^\+[1-9][0-9]{7,14}$")]


class QuotedLine(Contract):
    id: UUID
    version: Version
    variant_id: UUID
    quantity: Annotated[int, Field(strict=True, ge=1, le=20)]
    group_id: UUID | None
    slot_key: Annotated[str, Field(max_length=32)] | None
    product_id: UUID
    product_name: Annotated[str, Field(min_length=1, max_length=240)]
    sku: Annotated[str, Field(min_length=1, max_length=100)]
    specifications: dict[str, JsonValue]
    spec_version: Version
    unit_price_minor: Annotated[int, Field(strict=True, gt=0, le=9_000_000_000_000)]
    price_version: Version


class QuotedGroup(Contract):
    id: UUID
    version: Version
    name: Annotated[str, Field(min_length=1, max_length=100)]
    mode: Literal["complete_build", "parts_only"]
    requires_dedicated_gpu: bool
    source_build_id: UUID | None
    source_build_version: Version | None
    selection_hash: Digest
    spec_versions: dict[str, Version]
    ruleset_version: Annotated[str, Field(min_length=1, max_length=80)]
    status: Literal["compatible", "incompatible", "needs_review", "incomplete"]
    findings: list[dict[str, JsonValue]]
    evaluated_at: AwareDatetime


class CatalogQuote(MarketTerms):
    id: UUID
    operation_id: UUID
    customer_id: UUID
    cart_id: UUID
    cart_version: Version
    cart_fingerprint: Digest
    lines: list[QuotedLine] = Field(min_length=1, max_length=100)
    groups: list[QuotedGroup] = Field(max_length=100)
    subtotal_minor: Amount
    expires_at: AwareDatetime

    @model_validator(mode="after")
    def validate_snapshots(self) -> Self:
        group_ids = {g.id for g in self.groups}
        group_slots = set()
        if len(group_ids) != len(self.groups) or len({line.id for line in self.lines}) != len(
            self.lines
        ):
            raise ValueError("Quote line and group identifiers must be unique")
        for line in self.lines:
            if (line.group_id is None) != (line.slot_key is None):
                raise ValueError("Only grouped items carry slots")
            if line.group_id is not None:
                key = (line.group_id, line.slot_key)
                if line.group_id not in group_ids or key in group_slots:
                    raise ValueError("Grouped items require a valid distinct group slot")
                group_slots.add(key)
            if self.currency == "IRR" and line.unit_price_minor % 10:
                raise ValueError("IRR must be stated in whole tomans")
        if self.subtotal_minor != sum(line.unit_price_minor * line.quantity for line in self.lines):
            raise ValueError("Quoted line prices do not match the subtotal")
        return self


class DeliveryRate(MarketTerms):
    country: Country
    policy_version: Annotated[str, Field(min_length=1, max_length=80)]
    shipping_minor: Amount
    tax_basis_points: Annotated[int, Field(strict=True, ge=0, le=10000)]
    tax_included: bool
    shipping_taxable: bool

    @model_validator(mode="after")
    def validate_destination(self) -> Self:
        if self.market == "ir" and (self.country != "IR" or self.shipping_minor % 10):
            raise ValueError("The Iranian rate requires an Iranian destination and whole tomans")
        return self


class Discount(Contract):
    kind: Literal["fixed", "percentage"]
    value: Annotated[int, Field(strict=True, ge=1, le=9_000_000_000_000_000)]
    minimum_minor: Amount = 0
    maximum_minor: Amount | None = None

    @model_validator(mode="after")
    def validate_percentage(self) -> Self:
        if self.kind == "percentage" and self.value > 10_000:
            raise ValueError("Percentage discounts use basis points")
        return self


class Totals(MarketTerms):
    subtotal_minor: Amount
    discount_minor: Amount
    shipping_minor: Amount
    tax_minor: Amount
    tax_included: bool
    total_minor: Amount


def calculate_totals(
    quote: CatalogQuote, address: AddressSnapshot, rate: DeliveryRate, discount: Discount | None
) -> Totals:
    if (quote.market, quote.currency, address.country) != (
        rate.market,
        rate.currency,
        rate.country,
    ):
        raise CheckoutError("checkout.delivery_unavailable")
    quantum = 10 if quote.currency == "IRR" else 1
    subtotal = quote.subtotal_minor
    deduction = 0
    if discount is not None:
        if subtotal < discount.minimum_minor:
            raise CheckoutError("coupon.minimum_spend")
        raw = discount.value if discount.kind == "fixed" else subtotal * discount.value // 10_000
        deduction = min(raw, subtotal)
        if discount.maximum_minor is not None:
            deduction = min(deduction, discount.maximum_minor)
        deduction -= deduction % quantum
        if deduction == 0:
            raise CheckoutError("coupon.no_discount")
    net = subtotal - deduction
    taxable = net + (rate.shipping_minor if rate.shipping_taxable else 0)
    divisor = 10_000 + rate.tax_basis_points if rate.tax_included else 10_000
    tax = taxable * rate.tax_basis_points // divisor
    tax -= tax % quantum
    return Totals(
        market=quote.market,
        currency=quote.currency,
        subtotal_minor=subtotal,
        discount_minor=deduction,
        shipping_minor=rate.shipping_minor,
        tax_minor=tax,
        tax_included=rate.tax_included,
        total_minor=net + rate.shipping_minor + (0 if rate.tax_included else tax),
    )
