import asyncio
import sys
from uuid import NAMESPACE_URL, uuid5

import pytest

from nivaro_catalog.domain.contracts import (
    CPU,
    PSU,
    Case,
    Cooler,
    EvaluationRequest,
    Evidence,
    Localized,
    Memory,
    Motherboard,
    Selection,
    Storage,
    Variant,
)


@pytest.fixture(scope="session")
def event_loop_policy():
    # psycopg async requires SelectorEventLoop for provisional Windows checks.
    # The supported production runtime remains Linux/Python 3.13.
    if sys.platform == "win32":
        return asyncio.WindowsSelectorEventLoopPolicy()
    return asyncio.DefaultEventLoopPolicy()


@pytest.fixture
def complete_build():
    """Synthetic manufacturer facts for policy tests ONLY, never retail seed data."""
    specs = [
        CPU(
            model="TEST-CPU",
            socket="TEST-SOCKET",
            memory_generation="DDR5",
            max_memory_gb=256,
            max_package_power_w=150,
            integrated_graphics=True,
            included_cooler=False,
        ),
        Motherboard(
            socket="TEST-SOCKET",
            form_factor="ATX",
            memory_generation="DDR5",
            memory_slots=4,
            max_memory_gb=128,
            bios_revision="TEST-BIOS",
            verified_bios_revision="TEST-BIOS",
            verified_cpu_models=["TEST-CPU"],
            storage_interfaces={"NVMe": 2, "SATA": 4},
            storage_form_factors=["M.2-2280", "2.5"],
            power_connectors={"ATX24": 1, "EPS8": 1},
        ),
        Memory(generation="DDR5", modules=2, capacity_gb=32, height_mm=35),
        Storage(interface="NVMe", form_factor="M.2-2280", capacity_gb=1000),
        Case(
            motherboard_forms=["ATX"],
            psu_forms=["ATX"],
            max_psu_length_mm=180,
            max_gpu_length_mm=350,
            max_gpu_height_mm=160,
            expansion_slots=7,
            max_cooler_height_mm=170,
            drive_bays={"2.5": 2},
        ),
        PSU(
            wattage_w=750,
            form_factor="ATX",
            length_mm=160,
            connectors={"ATX24": 1, "EPS8": 2, "PCIe8": 2, "SATA": 4},
        ),
        Cooler(
            cooling_type="air",
            sockets=["TEST-SOCKET"],
            height_mm=155,
            max_memory_height_mm=40,
            approved_cpu_models=["TEST-CPU"],
        ),
    ]
    variants = {}
    selections = []
    for spec in specs:
        variant = Variant(
            id=uuid5(NAMESPACE_URL, "test/" + spec.kind),
            sku="TEST-" + spec.kind,
            packaging=Localized(fa="نمونهٔ آزمون", en="Synthetic test fixture"),
            specifications=spec,
            stock_kind="component",
            evidence=[
                Evidence(
                    url="https://example.test/spec",
                    checked_on="2026-10-27",
                    note="Synthetic test evidence, not real hardware",
                )
            ],
        )
        variants[variant.id] = variant
        selections.append(Selection(slot_key=spec.kind, role=spec.kind, variant_id=variant.id))
    return EvaluationRequest(market="ir", currency="IRR", selections=selections), variants
