"""Conservative, versioned compatibility policy. This module never reserves stock.

Rule semantics and deliberate coverage limits are documented in
docs/catalog/COMPATIBILITY_RULES.md. Manufacturer evidence belongs to each
versioned variant. Unknown geometry/BIOS/power data must not become a pass.
"""

import hashlib
import json
from collections import Counter
from datetime import UTC, datetime
from typing import Literal
from uuid import UUID

from .contracts import (
    CPU,
    GPU,
    PSU,
    Case,
    Cooler,
    Evaluation,
    EvaluationRequest,
    Finding,
    Localized,
    Memory,
    Motherboard,
    Peripheral,
    Selection,
    Status,
    Storage,
    Variant,
)

RULESET_VERSION = "nivaro-core-2026-10-27.1"
POWER_METHOD = (
    "ceil((CPU maximum package W + GPU board W + 100 W allowance) * 1.25); not measured draw"
)
OPTIONAL_ROLES = {"monitor", "keyboard", "mouse", "audio", "chair", "desk", "accessory"}


class SelectionError(ValueError):
    """A selection references unavailable data or a variant in the wrong role."""


def selection_hash(request: EvaluationRequest) -> str:
    payload = request.model_dump(mode="json", exclude={"previous"})
    payload["selections"] = sorted(payload["selections"], key=lambda row: row["slot_key"])
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def evaluate(
    request: EvaluationRequest,
    variants: dict[UUID, Variant],
    *,
    ruleset_version: str = RULESET_VERSION,
    evaluated_at: datetime | None = None,
) -> Evaluation:
    selected: dict[str, list[tuple[Selection, Variant]]] = {}
    for line in request.selections:
        variant = variants.get(line.variant_id)
        if variant is None:
            raise SelectionError("Selected variant is unavailable")
        spec = variant.specifications
        role = spec.role if isinstance(spec, Peripheral) else spec.kind
        if role != line.role:
            raise SelectionError("Variant does not belong to the requested component role")
        selected.setdefault(line.role, []).append((line, variant))

    findings: list[Finding] = []

    def record(code: str, status: Status, roles: list[str], fa: str, en: str) -> None:
        lines = [pair for role in roles for pair in selected.get(role, [])]
        evidence = [e for _, variant in lines for e in variant.evidence]
        actions = {
            "incompatible": (
                "قطعهٔ ناسازگار را جایگزین و دوباره بررسی کن.",
                "Replace the conflicting component and evaluate again.",
            ),
            "incomplete": ("قطعهٔ موردنیاز را انتخاب کن.", "Select the missing required component."),
            "needs_review": (
                "مشخصات یا تأییدیهٔ سازنده برای این ترکیب لازم است.",
                "Obtain manufacturer specifications or confirmation for this combination.",
            ),
            "compatible": (
                "با تغییر قطعات یا مشخصات، دوباره بررسی کن.",
                "Evaluate again when selections or specifications change.",
            ),
        }
        findings.append(
            Finding(
                code=code,
                status=status,
                slots=[line.slot_key for line, _ in lines] or roles,
                message=Localized(fa=fa, en=en),
                corrective_action=Localized(fa=actions[status][0], en=actions[status][1]),
                evidence=evidence,
                ruleset_version=ruleset_version,
            )
        )

    def check(code: str, roles: list[str], valid: bool | None, fa: str, en: str) -> None:
        if valid is not True:
            record(code, "needs_review" if valid is None else "incompatible", roles, fa, en)

    def fits(value: int | None, limit: int | None) -> bool | None:
        return None if value is None or limit is None else value <= limit

    def matches(value: str | None, other: str | None) -> bool | None:
        return None if value is None or other is None else value == other

    def includes(value: str | None, allowed: list[str] | None) -> bool | None:
        return None if value is None or allowed is None else value in allowed

    def one(role: str) -> object | None:
        rows = selected.get(role, [])
        return rows[0][1].specifications if rows else None

    for role in ("cpu", "motherboard", "memory", "storage", "case", "psu"):
        if role not in selected:
            record(
                "required." + role,
                "incomplete",
                [role],
                "یکی از قطعات اصلی انتخاب نشده است.",
                "A required core component has not been selected.",
            )
    for role, pairs in selected.items():
        if any(not variant.evidence for _, variant in pairs):
            record(
                "evidence.missing",
                "needs_review",
                [role],
                "منبع مشخصات این قطعه ثبت نشده است.",
                "Manufacturer evidence is missing for this component.",
            )
        if role in OPTIONAL_ROLES:
            record(
                "peripheral.connection",
                "needs_review",
                [role],
                "اتصال و سازگاری لوازم جانبی جداگانه بررسی شود.",
                "Peripheral connectivity and suitability need a separate check.",
            )

    cpu, board, case, psu, cooler, gpu = (
        one(r) for r in ("cpu", "motherboard", "case", "psu", "cooler", "gpu")
    )
    if isinstance(cpu, CPU):
        if "gpu" not in selected:
            if request.requires_dedicated_gpu or cpu.integrated_graphics is False:
                record(
                    "required.gpu",
                    "incomplete",
                    ["gpu", "cpu"],
                    "برای این انتخاب، کارت گرافیک مجزا لازم است.",
                    "This selection requires a dedicated graphics card.",
                )
            elif cpu.integrated_graphics is None:
                record(
                    "cpu.graphics_unknown",
                    "needs_review",
                    ["cpu"],
                    "وجود گرافیک داخلی تأیید نشده است.",
                    "Integrated graphics availability is unknown.",
                )
        if cooler is None:
            if cpu.included_cooler is False:
                record(
                    "required.cooler",
                    "incomplete",
                    ["cooler"],
                    "این پردازنده خنک‌کنندهٔ همراه ندارد.",
                    "This processor does not include a cooler.",
                )
            elif cpu.included_cooler is None:
                record(
                    "cpu.cooler_unknown",
                    "needs_review",
                    ["cpu"],
                    "وجود و کفایت خنک‌کنندهٔ همراه مشخص نیست.",
                    "Included cooling is not confirmed.",
                )
            elif isinstance(case, Case):
                check(
                    "cooler.included_clearance",
                    ["cpu", "case"],
                    fits(cpu.included_cooler_height_mm, case.max_cooler_height_mm),
                    "ارتفاع خنک‌کنندهٔ همراه باید با کیس تطبیق داده شود.",
                    "The included cooler must fit the case height limit.",
                )
    elif cooler is None:
        record(
            "required.cooler",
            "incomplete",
            ["cooler"],
            "خنک‌کنندگی مناسب هنوز مشخص نیست.",
            "Adequate cooling has not been established.",
        )

    if isinstance(cpu, CPU) and isinstance(board, Motherboard):
        check(
            "cpu.socket",
            ["cpu", "motherboard"],
            matches(cpu.socket, board.socket),
            "سوکت پردازنده و مادربرد باید یکسان و تأییدشده باشد.",
            "CPU and motherboard sockets must be known and match.",
        )
        bios_known = (
            board.bios_revision is not None and board.bios_revision == board.verified_bios_revision
        )
        supported = (
            cpu.model in board.verified_cpu_models
            if bios_known and board.verified_cpu_models is not None
            else None
        )
        check(
            "cpu.bios_support",
            ["cpu", "motherboard"],
            supported,
            "پشتیبانی پردازنده به نسخهٔ واقعی بایوس وابسته است.",
            "CPU support must be verified for the actual installed BIOS revision.",
        )

    memory_rows = selected.get("memory", [])
    total_modules, total_memory = 0, 0
    memory_totals_known = True
    for line, variant in memory_rows:
        ram = variant.specifications
        assert isinstance(ram, Memory)
        if ram.modules is None or ram.capacity_gb is None:
            memory_totals_known = False
        else:
            total_modules += ram.modules * line.quantity
            total_memory += ram.capacity_gb * line.quantity
        if isinstance(board, Motherboard):
            check(
                "memory.board_generation",
                ["memory", "motherboard"],
                matches(ram.generation, board.memory_generation),
                "نسل رم و مادربرد باید سازگار باشد.",
                "Memory generation must match the motherboard.",
            )
        if isinstance(cpu, CPU):
            check(
                "memory.cpu_generation",
                ["memory", "cpu"],
                matches(ram.generation, cpu.memory_generation),
                "نسل رم باید توسط پردازنده پشتیبانی شود.",
                "Memory generation must be supported by the CPU.",
            )
        if isinstance(cooler, Cooler) and cooler.cooling_type == "air":
            check(
                "memory.cooler_clearance",
                ["memory", "cooler"],
                fits(ram.height_mm, cooler.max_memory_height_mm),
                "فضای رم زیر خنک‌کننده باید کافی باشد.",
                "Memory must fit the cooler RAM clearance.",
            )
    if memory_rows and isinstance(board, Motherboard):
        check(
            "memory.slot_count",
            ["memory", "motherboard"],
            fits(total_modules if memory_totals_known else None, board.memory_slots),
            "تعداد ماژول‌ها باید در اسلات‌های مادربرد جا شود.",
            "The total module count must fit the motherboard slots.",
        )
        check(
            "memory.capacity",
            ["memory", "motherboard"],
            fits(total_memory if memory_totals_known else None, board.max_memory_gb),
            "ظرفیت کل رم باید در محدودهٔ مادربرد باشد.",
            "Total kit capacity must fit the motherboard limit.",
        )
    if memory_rows and isinstance(cpu, CPU):
        check(
            "memory.cpu_capacity",
            ["memory", "cpu"],
            fits(total_memory if memory_totals_known else None, cpu.max_memory_gb),
            "ظرفیت رم باید در محدودهٔ پردازنده باشد.",
            "Total memory must fit the CPU capacity limit.",
        )
    if len({variant.id for _, variant in memory_rows}) > 1:
        record(
            "memory.mixed_kits",
            "needs_review",
            ["memory"],
            "ترکیب کیت‌های متفاوت نیازمند بررسی جداگانه است.",
            "Mixing distinct memory kits requires separate verification.",
        )

    if isinstance(case, Case):
        if isinstance(board, Motherboard):
            check(
                "case.motherboard",
                ["case", "motherboard"],
                includes(board.form_factor, case.motherboard_forms),
                "فرم مادربرد باید در کیس پشتیبانی شود.",
                "The case must support the motherboard form factor.",
            )
        if isinstance(psu, PSU):
            check(
                "case.psu_form",
                ["case", "psu"],
                includes(psu.form_factor, case.psu_forms),
                "فرم پاور باید با کیس سازگار باشد.",
                "The case must support the PSU form factor.",
            )
            check(
                "case.psu_length",
                ["case", "psu"],
                fits(psu.length_mm, case.max_psu_length_mm),
                "طول پاور باید در فضای کیس جا شود.",
                "The PSU must fit the case length clearance.",
            )
        if isinstance(gpu, GPU):
            for dimension, value, limit in [
                ("length", gpu.length_mm, case.max_gpu_length_mm),
                ("height", gpu.height_mm, case.max_gpu_height_mm),
                ("slots", gpu.slots, case.expansion_slots),
            ]:
                check(
                    "case.gpu_" + dimension,
                    ["case", "gpu"],
                    fits(value, limit),
                    "ابعاد کارت گرافیک باید با فضای مؤثر کیس سازگار باشد.",
                    "GPU dimensions must fit the effective case clearances.",
                )
    if isinstance(cooler, Cooler):
        if isinstance(cpu, CPU):
            check(
                "cooler.socket",
                ["cooler", "cpu"],
                includes(cpu.socket, cooler.sockets),
                "پایهٔ خنک‌کننده باید سوکت پردازنده را پشتیبانی کند.",
                "The cooler mounting kit must support the CPU socket.",
            )
            check(
                "cooler.capacity",
                ["cooler", "cpu"],
                includes(cpu.model, cooler.approved_cpu_models),
                "کفایت خنک‌کننده برای این مدل نیازمند تأیید سازنده است.",
                "Cooling adequacy needs manufacturer approval for this CPU model.",
            )
        if cooler.cooling_type == "air" and isinstance(case, Case):
            check(
                "cooler.height",
                ["cooler", "case"],
                fits(cooler.height_mm, case.max_cooler_height_mm),
                "ارتفاع خنک‌کننده باید با کیس سازگار باشد.",
                "The air cooler must fit the case height limit.",
            )
        elif cooler.cooling_type != "air":
            record(
                "cooler.radiator_layout",
                "needs_review",
                ["cooler", "case", "gpu", "memory"],
                "جانمایی رادیاتور، فن و تداخل قطعات هنوز قابل تأیید خودکار نیست.",
                "Radiator, fan and component interference require a layout review; this ruleset cannot certify them.",
            )

    interfaces: Counter[str] = Counter()
    bays: Counter[str] = Counter()
    for line, variant in selected.get("storage", []):
        disk = variant.specifications
        assert isinstance(disk, Storage)
        if disk.interface is None or disk.form_factor is None:
            record(
                "storage.unknown",
                "needs_review",
                ["storage"],
                "رابط یا فرم حافظه مشخص نیست.",
                "Storage interface or form factor is unknown.",
            )
        else:
            interfaces[disk.interface] += line.quantity
            if disk.interface == "SATA":
                bays[disk.form_factor] += line.quantity
        if isinstance(board, Motherboard):
            check(
                "storage.form",
                ["storage", "motherboard"],
                includes(disk.form_factor, board.storage_form_factors),
                "فرم حافظه باید پشتیبانی شود.",
                "The storage form factor must be supported.",
            )
    if isinstance(board, Motherboard):
        for interface, count in interfaces.items():
            capacity = (
                board.storage_interfaces.get(interface, 0)
                if board.storage_interfaces is not None
                else None
            )
            check(
                "storage.ports",
                ["storage", "motherboard"],
                fits(count, capacity),
                "تعداد و رابط حافظه باید با درگاه‌های قابل‌استفاده تطبیق داده شود.",
                "Storage counts must fit the usable interface ports, including lane-sharing limits.",
            )
    if isinstance(case, Case):
        for form, count in bays.items():
            capacity = case.drive_bays.get(form, 0) if case.drive_bays is not None else None
            check(
                "storage.bays",
                ["storage", "case"],
                fits(count, capacity),
                "تعداد جایگاه نصب درایو باید کافی باشد.",
                "The case must have enough drive mounting bays.",
            )

    estimated_power: int | None = None
    if isinstance(cpu, CPU) and isinstance(psu, PSU):
        gpu_draw = gpu.board_power_w if isinstance(gpu, GPU) else 0
        if cpu.max_package_power_w is not None and gpu_draw is not None:
            estimated_power = ((cpu.max_package_power_w + gpu_draw + 100) * 125 + 99) // 100
        check(
            "power.capacity",
            ["cpu", "gpu", "psu"],
            fits(estimated_power, psu.wattage_w),
            "توان پاور با حاشیهٔ تخمینی بررسی می‌شود؛ توان نامعلوم قابل تأیید نیست.",
            "PSU capacity needs a conservative estimate; unknown power cannot pass.",
        )
        if isinstance(gpu, GPU):
            check(
                "power.gpu_recommendation",
                ["gpu", "psu"],
                fits(gpu.recommended_psu_w, psu.wattage_w),
                "حداقل پاور پیشنهادی سازندهٔ گرافیک باید رعایت شود.",
                "Meet the GPU manufacturer's minimum recommended PSU rating.",
            )
    if isinstance(psu, PSU):
        required_connectors: Counter[str] = Counter()
        for role, spec in (("motherboard", board), ("gpu", gpu)):
            if isinstance(spec, (Motherboard, GPU)):
                if spec.power_connectors is None:
                    record(
                        "power.connectors_unknown",
                        "needs_review",
                        [role, "psu"],
                        "کانکتورهای برق موردنیاز مشخص نیست.",
                        "Required power connectors are unknown.",
                    )
                else:
                    required_connectors.update(spec.power_connectors)
        if interfaces.get("SATA"):
            required_connectors["SATA"] += interfaces["SATA"]
        for connector, count in required_connectors.items():
            available = psu.connectors.get(connector, 0) if psu.connectors is not None else None
            check(
                "power.connector_count",
                ["motherboard", "gpu", "storage", "psu"],
                fits(count, available),
                "نوع و تعداد کانکتورهای پاور باید کافی باشد؛ تبدیل فرض نمی‌شود.",
                "PSU connector types and counts must suffice; adapters are not assumed.",
            )

    core_findings = [f for f in findings if f.code != "peripheral.connection"]
    priority: list[Status] = ["incompatible", "incomplete", "needs_review"]
    status: Status = next(
        (s for s in priority if any(f.status == s for f in core_findings)), "compatible"
    )
    if status == "compatible":
        record(
            "core.checked",
            "compatible",
            list(selected),
            "کنترل‌های اصلی این نسخه با داده‌های ثبت‌شده گذرانده شدند؛ بررسی فیزیکی نهایی همچنان لازم است.",
            "This ruleset's core checks pass for the recorded facts; final physical verification remains necessary.",
        )

    versions = {
        str(line.variant_id): variants[line.variant_id].spec_version for line in request.selections
    }
    fingerprint = selection_hash(request)
    stale: list[Literal["selection_changed", "specifications_changed", "rules_changed"]] = []
    if request.previous is not None:
        if request.previous.selection_hash != fingerprint:
            stale.append("selection_changed")
        if request.previous.spec_versions != versions:
            stale.append("specifications_changed")
        if request.previous.ruleset_version != ruleset_version:
            stale.append("rules_changed")
    component_total = peripheral_total = 0
    unpriced, unavailable = [], []
    quantities: Counter[UUID] = Counter()
    for line in request.selections:
        quantities[line.variant_id] += line.quantity
    for line in request.selections:
        variant = variants[line.variant_id]
        offer = next((o for o in variant.offers if o.market == request.market), None)
        if offer is None:
            unpriced.append(line.slot_key)
        elif line.role in OPTIONAL_ROLES:
            peripheral_total += offer.amount_minor * line.quantity
        else:
            component_total += offer.amount_minor * line.quantity
        if (
            offer is None
            or not offer.available_for_sale
            or not variant.stock_verified
            or quantities[variant.id] > variant.on_hand - variant.reserved
        ):
            unavailable.append(line.slot_key)
    return Evaluation(
        mode=request.mode,
        market=request.market,
        currency=request.currency,
        selection_hash=fingerprint,
        spec_versions=versions,
        ruleset_version=ruleset_version,
        status=status,
        findings=findings,
        evaluated_at=evaluated_at or datetime.now(UTC),
        stale_reasons=stale,
        estimated_power_w=estimated_power,
        power_method=POWER_METHOD,
        component_subtotal_minor=component_total,
        peripheral_subtotal_minor=peripheral_total,
        unpriced_slots=unpriced,
        unavailable_slots=unavailable,
    )
