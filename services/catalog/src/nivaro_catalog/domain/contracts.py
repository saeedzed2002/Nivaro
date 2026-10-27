from datetime import date, datetime
from typing import Annotated, Literal, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, model_validator

Positive = Annotated[int, Field(strict=True, gt=0, le=1_000_000)]
MoneyAmount = Annotated[int, Field(strict=True, gt=0, le=9_000_000_000_000)]
Market = Literal["ir", "international"]
Currency = Literal["IRR", "USD"]
Status = Literal["compatible", "incompatible", "needs_review", "incomplete"]
Slot = Literal[
    "cpu",
    "motherboard",
    "memory",
    "storage",
    "case",
    "psu",
    "cooler",
    "gpu",
    "monitor",
    "keyboard",
    "mouse",
    "audio",
    "chair",
    "desk",
    "accessory",
]


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Localized(Contract):
    fa: Annotated[str, Field(min_length=1, max_length=4000)]
    en: Annotated[str, Field(min_length=1, max_length=4000)]


class Evidence(Contract):
    url: HttpUrl
    checked_on: date
    note: Annotated[str, Field(min_length=1, max_length=500)]


class MarketContext(Contract):
    market: Market
    currency: Currency

    @model_validator(mode="after")
    def matching_currency(self) -> Self:
        if self.currency != {"ir": "IRR", "international": "USD"}[self.market]:
            raise ValueError("Currency must match the independent market price book")
        return self


class Offer(MarketContext):
    amount_minor: MoneyAmount
    price_version: Positive = 1
    available_for_sale: bool = False
    reference_only: bool = True
    source: Evidence
    seller: Annotated[str, Field(min_length=1, max_length=120)]

    @model_validator(mode="after")
    def money_policy(self) -> Self:
        if self.currency == "IRR" and self.amount_minor % 10:
            raise ValueError("IRR amounts must be whole tomans (multiples of ten rials)")
        if self.reference_only and self.available_for_sale:
            raise ValueError("Research references cannot be offered for sale")
        return self


class CPU(Contract):
    kind: Literal["cpu"] = "cpu"
    model: str
    socket: str | None = None
    memory_generation: Literal["DDR4", "DDR5"] | None = None
    max_memory_gb: Positive | None = None
    cores: Positive | None = None
    threads: Positive | None = None
    tdp_w: Positive | None = None
    # TDP is not a measured or maximum package draw. Never substitute it here.
    max_package_power_w: Positive | None = None
    integrated_graphics: bool | None = None
    included_cooler: bool | None = None
    included_cooler_height_mm: Positive | None = None


class Motherboard(Contract):
    kind: Literal["motherboard"] = "motherboard"
    socket: str | None = None
    form_factor: str | None = None
    memory_generation: Literal["DDR4", "DDR5"] | None = None
    memory_slots: Positive | None = None
    max_memory_gb: Positive | None = None
    bios_revision: str | None = None
    # Support list is evidence for one actual BIOS revision, not just a socket.
    verified_bios_revision: str | None = None
    verified_cpu_models: list[str] | None = None
    storage_interfaces: dict[str, Positive] | None = None
    storage_form_factors: list[str] | None = None
    power_connectors: dict[str, Positive] | None = None


class Memory(Contract):
    kind: Literal["memory"] = "memory"
    generation: Literal["DDR4", "DDR5"] | None = None
    modules: Positive | None = None
    capacity_gb: Positive | None = None
    height_mm: Positive | None = None


class Storage(Contract):
    kind: Literal["storage"] = "storage"
    interface: str | None = None
    form_factor: str | None = None
    capacity_gb: Positive | None = None


class Case(Contract):
    kind: Literal["case"] = "case"
    motherboard_forms: list[str] | None = None
    psu_forms: list[str] | None = None
    max_psu_length_mm: Positive | None = None
    max_gpu_length_mm: Positive | None = None
    max_gpu_height_mm: Positive | None = None
    expansion_slots: Positive | None = None
    max_cooler_height_mm: Positive | None = None
    # Case-dependent SATA drive mounting must also be checked.
    drive_bays: dict[str, Positive] | None = None


class PSU(Contract):
    kind: Literal["psu"] = "psu"
    wattage_w: Positive | None = None
    form_factor: str | None = None
    length_mm: Positive | None = None
    connectors: dict[str, Positive] | None = None


class Cooler(Contract):
    kind: Literal["cooler"] = "cooler"
    cooling_type: Literal["air", "liquid"] | None = None
    sockets: list[str] | None = None
    height_mm: Positive | None = None
    max_memory_height_mm: Positive | None = None
    approved_cpu_models: list[str] | None = None


class GPU(Contract):
    kind: Literal["gpu"] = "gpu"
    length_mm: Positive | None = None
    height_mm: Positive | None = None
    slots: Positive | None = None
    board_power_w: Positive | None = None
    recommended_psu_w: Positive | None = None
    power_connectors: dict[str, Positive] | None = None
    vram_gb: Positive | None = None


class Peripheral(Contract):
    kind: Literal["peripheral"] = "peripheral"
    role: Literal["monitor", "keyboard", "mouse", "audio", "chair", "desk", "accessory"]
    connection: str | None = None


class Prebuilt(Contract):
    kind: Literal["prebuilt"] = "prebuilt"
    cpu_model: str | None = None
    gpu_model: str | None = None
    memory_gb: Positive | None = None
    storage_gb: Positive | None = None
    # Descriptions are not component inventory allocations.
    component_descriptions: list[str] = Field(default_factory=list, max_length=32)


Specifications = Annotated[
    CPU | Motherboard | Memory | Storage | Case | PSU | Cooler | GPU | Peripheral | Prebuilt,
    Field(discriminator="kind"),
]


class Variant(Contract):
    id: UUID
    sku: Annotated[str, Field(min_length=1, max_length=100)]
    packaging: Localized
    specifications: Specifications
    spec_version: Positive = 1
    evidence: list[Evidence] = Field(default_factory=list, max_length=20)
    stock_kind: Literal["component", "accessory", "stocked_prebuilt"]
    on_hand: Annotated[int, Field(strict=True, ge=0, le=1_000_000)] = 0
    reserved: Annotated[int, Field(strict=True, ge=0, le=1_000_000)] = 0
    stock_verified: bool = False
    offers: list[Offer] = Field(default_factory=list, max_length=2)

    @model_validator(mode="after")
    def invariants(self) -> Self:
        if self.reserved > self.on_hand:
            raise ValueError("Reserved units cannot exceed physical stock")
        if (self.stock_kind == "stocked_prebuilt") != (self.specifications.kind == "prebuilt"):
            raise ValueError("Finished PC stock must belong only to a prebuilt SKU")
        if (self.stock_kind == "accessory") != (self.specifications.kind == "peripheral"):
            raise ValueError("Accessory stock requires peripheral specifications")
        if len({o.market for o in self.offers}) != len(self.offers):
            raise ValueError("Only one offer per variant and market")
        return self


class Category(Contract):
    id: UUID
    slug: str
    name: Localized
    image: str
    parent_id: UUID | None = None


class Product(Contract):
    id: UUID
    slug: str
    name: str
    description: Localized
    category: str
    brand: str
    image: str
    image_kind: Literal["illustration", "exact_sku"] = "illustration"
    highlights: list[str] = Field(default_factory=list)
    variants: list[Variant] = Field(min_length=1, max_length=100)


class Selection(Contract):
    slot_key: Annotated[str, Field(pattern=r"^[a-z]+(:[1-9][0-9]?)?$", max_length=32)]
    role: Slot
    variant_id: UUID
    quantity: Annotated[int, Field(strict=True, ge=1, le=10)] = 1

    @model_validator(mode="after")
    def slot_matches_role(self) -> Self:
        if self.slot_key.split(":")[0] != self.role:
            raise ValueError("Slot key must start with its role")
        if self.role not in {"memory", "storage", "accessory"} and self.quantity != 1:
            raise ValueError("Only one unit of this role is allowed per system")
        return self


class Revision(Contract):
    selection_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    spec_versions: dict[str, Positive]
    ruleset_version: str = Field(min_length=1, max_length=80)


class EvaluationRequest(MarketContext):
    mode: Literal["complete_build", "parts_only"] = "complete_build"
    requires_dedicated_gpu: bool = False
    selections: list[Selection] = Field(default_factory=list, max_length=32)
    previous: Revision | None = None

    @model_validator(mode="after")
    def distinct_slots(self) -> Self:
        if len({s.slot_key for s in self.selections}) != len(self.selections):
            raise ValueError("Slot keys must be unique")
        for role in {s.role for s in self.selections} - {"memory", "storage", "accessory"}:
            if sum(s.role == role for s in self.selections) > 1:
                raise ValueError(f"Multiple {role} slots are not supported")
        return self


class Finding(Contract):
    code: str
    status: Status
    slots: list[str]
    message: Localized
    corrective_action: Localized
    evidence: list[Evidence]
    ruleset_version: str


class Evaluation(Revision, MarketContext):
    mode: Literal["complete_build", "parts_only"]
    status: Status
    findings: list[Finding]
    evaluated_at: datetime
    stale_reasons: list[Literal["selection_changed", "specifications_changed", "rules_changed"]]
    estimated_power_w: int | None
    power_method: str
    # Research subtotal is not a quote and includes only prices known in this market.
    component_subtotal_minor: int
    peripheral_subtotal_minor: int
    unpriced_slots: list[str]
    unavailable_slots: list[str]
    price_basis: Literal["reference_only_not_payable"] = "reference_only_not_payable"
    shipping_minor: None = None
    tax_minor: None = None
    assembly_fee_minor: None = None
    reserves_stock: Literal[False] = False


class BuildTemplate(Contract):
    """Virtual composition deliberately has neither stock counters nor a parent offer."""

    id: UUID
    name: Localized
    selections: list[Selection] = Field(max_length=32)
    version: Positive = 1
