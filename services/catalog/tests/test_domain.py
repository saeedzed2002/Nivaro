from uuid import uuid4

import pytest
from pydantic import ValidationError

from nivaro_catalog.domain.contracts import (
    GPU,
    BuildTemplate,
    EvaluationRequest,
    Localized,
    Offer,
    Prebuilt,
    Revision,
    Selection,
    Variant,
)
from nivaro_catalog.domain.evaluation import SelectionError, evaluate, selection_hash
from nivaro_catalog.domain.search import normalize_search


def revision(result):
    return Revision(
        **result.model_dump(include={"selection_hash", "spec_versions", "ruleset_version"})
    )


def spec(variants, role):
    return next(v.specifications for v in variants.values() if v.specifications.kind == role)


def test_complete_synthetic_air_cooled_build_passes_without_claiming_sale(complete_build):
    request, variants = complete_build
    result = evaluate(request, variants)
    assert result.status == "compatible"
    assert result.estimated_power_w == 313
    assert len(result.unpriced_slots) == 7
    assert result.unavailable_slots == [s.slot_key for s in request.selections]
    assert result.reserves_stock is False
    assert result.tax_minor is None and result.shipping_minor is None


def test_empty_build_is_incomplete():
    result = evaluate(EvaluationRequest(market="ir", currency="IRR"), {})
    assert result.status == "incomplete"
    assert "required.cpu" in {f.code for f in result.findings}


@pytest.mark.parametrize(
    "role,field,value,code",
    [
        ("cpu", "socket", "WRONG", "cpu.socket"),
        ("memory", "generation", "DDR4", "memory.board_generation"),
        ("memory", "modules", 5, "memory.slot_count"),
        ("memory", "capacity_gb", 256, "memory.capacity"),
        ("memory", "height_mm", 60, "memory.cooler_clearance"),
        ("psu", "length_mm", 190, "case.psu_length"),
        ("cooler", "height_mm", 200, "cooler.height"),
        ("psu", "wattage_w", 250, "power.capacity"),
        ("psu", "connectors", {}, "power.connector_count"),
        ("storage", "interface", "UNSUPPORTED", "storage.ports"),
    ],
)
def test_hard_conflicts(complete_build, role, field, value, code):
    request, variants = complete_build
    setattr(spec(variants, role), field, value)
    result = evaluate(request, variants)
    assert result.status == "incompatible"
    assert any(f.code == code and f.status == "incompatible" for f in result.findings)


@pytest.mark.parametrize(
    "role,field",
    [
        ("cpu", "socket"),
        ("cpu", "max_package_power_w"),
        ("motherboard", "bios_revision"),
        ("motherboard", "verified_bios_revision"),
        ("motherboard", "verified_cpu_models"),
        ("motherboard", "memory_slots"),
        ("motherboard", "storage_interfaces"),
        ("case", "max_psu_length_mm"),
        ("cooler", "approved_cpu_models"),
        ("psu", "connectors"),
        ("memory", "modules"),
    ],
)
def test_missing_facts_never_pass(complete_build, role, field):
    request, variants = complete_build
    setattr(spec(variants, role), field, None)
    assert evaluate(request, variants).status == "needs_review"


def test_socket_alone_and_tdp_never_establish_support(complete_build):
    request, variants = complete_build
    spec(variants, "motherboard").bios_revision = "NEW-UNVERIFIED-BIOS"
    cpu = spec(variants, "cpu")
    cpu.max_package_power_w = None
    cpu.tdp_w = 65
    result = evaluate(request, variants)
    assert result.status == "needs_review" and result.estimated_power_w is None


def test_liquid_layout_is_not_falsely_certified(complete_build):
    request, variants = complete_build
    spec(variants, "cooler").cooling_type = "liquid"
    assert evaluate(request, variants).status == "needs_review"


def test_missing_evidence_never_passes(complete_build):
    request, variants = complete_build
    next(iter(variants.values())).evidence = []
    assert evaluate(request, variants).status == "needs_review"


def test_integrated_graphics_and_cooling_requirements(complete_build):
    request, variants = complete_build
    spec(variants, "cpu").integrated_graphics = False
    request.selections = [s for s in request.selections if s.role != "cooler"]
    result = evaluate(request, variants)
    assert result.status == "incomplete"
    assert {"required.gpu", "required.cooler"} <= {f.code for f in result.findings}


def test_parts_only_does_not_hide_a_conflict(complete_build):
    request, variants = complete_build
    request.mode = "parts_only"
    spec(variants, "cpu").socket = "WRONG"
    assert evaluate(request, variants).status == "incompatible"


def test_fingerprint_order_independent_but_role_quantity_market_mode_bound(complete_build):
    request, variants = complete_build
    result = evaluate(request, variants)
    request.previous = revision(result)
    request.selections.reverse()
    assert selection_hash(request) == result.selection_hash
    assert evaluate(request, variants).stale_reasons == []
    request.selections[0].slot_key += ":2"
    assert "selection_changed" in evaluate(request, variants).stale_reasons
    request.selections[0].slot_key = request.selections[0].role
    request.mode = "parts_only"
    assert selection_hash(request) != result.selection_hash
    request.mode = "complete_build"
    request.market, request.currency = "international", "USD"
    assert selection_hash(request) != result.selection_hash


def test_changed_rules_and_specs_invalidate_previous_result(complete_build):
    request, variants = complete_build
    request.previous = revision(evaluate(request, variants))
    next(iter(variants.values())).spec_version += 1
    result = evaluate(request, variants, ruleset_version="test-new-rules")
    assert set(result.stale_reasons) == {"specifications_changed", "rules_changed"}


def test_kit_quantity_aggregates_modules(complete_build):
    request, variants = complete_build
    next(s for s in request.selections if s.role == "memory").quantity = 3
    assert any(f.code == "memory.slot_count" for f in evaluate(request, variants).findings)


def test_unknown_and_wrong_role_are_rejected(complete_build):
    request, variants = complete_build
    request.selections[0].variant_id = uuid4()
    with pytest.raises(SelectionError):
        evaluate(request, variants)
    request.selections[0].variant_id = next(
        v.id for v in variants.values() if v.specifications.kind == "psu"
    )
    with pytest.raises(SelectionError):
        evaluate(request, variants)


def test_input_bounds_and_duplicate_slots(complete_build):
    request, _ = complete_build
    with pytest.raises(ValidationError):
        EvaluationRequest(market="ir", currency="USD")
    with pytest.raises(ValidationError):
        EvaluationRequest(market="ir", currency="IRR", selections=request.selections * 2)
    with pytest.raises(ValidationError):
        Selection(slot_key="memory", role="memory", variant_id=uuid4(), quantity=True)
    with pytest.raises(ValidationError):
        Selection(slot_key="cpu", role="memory", variant_id=uuid4())


def test_money_and_reference_invariants():
    data = dict(
        market="ir",
        currency="IRR",
        amount_minor=1000,
        seller="TEST",
        source={"url": "https://example.test", "checked_on": "2026-10-27", "note": "Synthetic"},
    )
    assert Offer(**data).amount_minor == 1000
    for invalid in (
        {"amount_minor": 999},
        {"amount_minor": 0},
        {"amount_minor": 1000.0},
        {"amount_minor": True},
        {"currency": "USD"},
        {"available_for_sale": True},
    ):
        with pytest.raises(ValidationError):
            Offer(**(data | invalid))


def test_reference_totals_and_repeated_sku_stock(complete_build):
    request, variants = complete_build
    storage = next(v for v in variants.values() if v.specifications.kind == "storage")
    storage.on_hand, storage.stock_verified = 1, True
    storage.offers = [
        Offer(
            market="ir",
            currency="IRR",
            amount_minor=2000,
            seller="TEST",
            reference_only=False,
            available_for_sale=True,
            source=storage.evidence[0],
        )
    ]
    request.selections.append(
        Selection(slot_key="storage:2", role="storage", variant_id=storage.id)
    )
    result = evaluate(request, variants)
    assert result.component_subtotal_minor == 4000
    assert {"storage", "storage:2"} <= set(result.unavailable_slots)
    request.market, request.currency = "international", "USD"
    result = evaluate(request, variants)
    assert result.component_subtotal_minor == 0 and "storage" in result.unpriced_slots
    assert storage.on_hand == 1 and storage.reserved == 0


def test_virtual_parent_cannot_hold_stock_or_price(complete_build):
    request, _ = complete_build
    with pytest.raises(ValidationError):
        BuildTemplate(
            id=uuid4(),
            name=Localized(fa="آزمون", en="Test"),
            selections=request.selections,
            on_hand=1,
        )
    with pytest.raises(ValidationError):
        Variant(
            id=uuid4(),
            sku="TEST-PC",
            packaging=Localized(fa="آزمون", en="Test"),
            specifications=Prebuilt(),
            stock_kind="component",
        )


def test_persian_search_preserves_display():
    original = "  كيبورد\u200cگيمينگ   يک  "
    assert normalize_search(original) == "کیبورد گیمینگ یک"
    assert original.startswith("  ك")


@pytest.mark.parametrize(
    "changed,value,expected",
    [
        ("length_mm", 400, "incompatible"),
        ("height_mm", 200, "incompatible"),
        ("slots", 8, "incompatible"),
        ("board_power_w", None, "needs_review"),
        ("recommended_psu_w", 1000, "incompatible"),
        ("power_connectors", {"PCIe8": 3}, "incompatible"),
        ("length_mm", 300, "compatible"),
    ],
)
def test_dedicated_gpu_fit_power_and_unknowns(complete_build, changed, value, expected):
    request, variants = complete_build
    gpu = GPU(
        length_mm=300,
        height_mm=140,
        slots=3,
        board_power_w=200,
        recommended_psu_w=650,
        power_connectors={"PCIe8": 2},
    )
    setattr(gpu, changed, value)
    variant = Variant(
        id=uuid4(),
        sku="TEST-GPU",
        packaging=Localized(fa="آزمون", en="Test"),
        specifications=gpu,
        stock_kind="component",
        evidence=next(iter(variants.values())).evidence,
    )
    variants[variant.id] = variant
    request.requires_dedicated_gpu = True
    request.selections.append(Selection(slot_key="gpu", role="gpu", variant_id=variant.id))
    assert evaluate(request, variants).status == expected


def test_sata_bays_and_power_are_aggregated(complete_build):
    request, variants = complete_build
    storage = spec(variants, "storage")
    storage.interface, storage.form_factor = "SATA", "2.5"
    next(s for s in request.selections if s.role == "storage").quantity = 3
    result = evaluate(request, variants)
    assert result.status == "incompatible"
    assert any(f.code == "storage.bays" for f in result.findings)


def test_cpu_memory_capacity_cannot_be_exceeded(complete_build):
    request, variants = complete_build
    spec(variants, "cpu").max_memory_gb = 16
    assert any(f.code == "memory.cpu_capacity" for f in evaluate(request, variants).findings)
