# Catalog evaluation policy — P02 foundation

Ruleset: `nivaro-core-2026-10-27.1`. Implementation: `services/catalog/src/nivaro_catalog/domain/evaluation.py`.

This is a conservative first ruleset, not a manufacturer certification. A variant's typed facts, specification revision and dated source URLs are inputs owned by catalog. Test fixtures are synthetic and must never be seeded as real products or advertised as sourced hardware. No state, inventory reservation, payment or cart write occurs during evaluation.

## Rules

| Check | Required evidence / behavior |
| --- | --- |
| Required parts | CPU, motherboard, memory, storage, case, PSU and adequate cooling. Dedicated GPU is required only by requested workflow or lack of CPU graphics. Unknown integrated graphics/cooler availability needs review. |
| CPU / board | Socket match plus exact CPU model in support data verified for the actual BIOS revision. Matching socket or family alone cannot pass. Missing actual BIOS stays unknown. |
| Memory | CPU/board generation, aggregate module count and kit capacity, cooler RAM clearance. Quantity means kits; each kit carries its module count and total capacity. |
| Mechanical fit | Board and PSU form factors, PSU length, GPU length/height/slot width, air cooler height. Case dimensions must reflect the effective configuration, not an obstructed nominal clearance. |
| Cooling | Correct socket mounting and manufacturer approval for the CPU model. Liquid/radiator combinations always need review in this version: radiator thickness, fans, placement and interference are not yet certified. No TDP-only cooler equivalence. |
| Storage | Form factor, usable interface/slot counts, SATA drive bays and power connectors. Board facts must account for shared lanes/disabled ports; missing usable counts need review. |
| PSU | Sum CPU maximum package power, GPU board power and a 100 W allowance, multiply by 1.25 and round up. Meet both that estimate and the GPU maker's PSU recommendation; check connector type/count without assuming adapters. CPU TDP is never substituted for maximum package power. |
| Peripherals | Separate subtotal and explicit connectivity advisory; not a guarantee of display cables, bandwidth or peripheral features. |

Power is an intentionally conservative project policy, not a measured consumption or FPS claim. The 100 W allowance and 25% margin are policy choices, not manufacturer figures. Missing input yields no estimate. This first version does not verify overclocking, QVL/speed profiles, PCIe bandwidth/performance, adapter safety, wiring, firmware outside the recorded BIOS, or complex liquid layouts. Revalidation after final physical inspection is still required.

## Identity and freshness

Canonical SHA-256 includes market, currency, mode, dedicated-GPU requirement and sorted exact slot/variant/quantity selections. Response carries the selected specification revisions and immutable ruleset revision. Changing any such input invalidates prior evidence. Price revisions deliberately do not establish compatibility; P06 quotes will additionally bind offer revisions and eligibility. An evaluation never guarantees price or reserves inventory.

Hard conflict has priority over missing parts, which have priority over unknown checks. Optional peripheral advisories remain visible without masking the core status. An incomplete or uncertain parts-only selection is never relabeled a compatible assembled system.

Subtotal sums only known same-market offers, separates core/peripherals, and lists unpriced/unavailable slots. It is explicitly non-payable research pricing. Shipping, tax and assembly fees remain pending, not zero. All units of a repeated physical variant are aggregated when checking availability.

Finished prebuilt SKUs hold their own stock; their internal descriptions are not stock allocations. Virtual templates have only component selections and cannot accept a parent price or stock counter.

## Source baseline

Manufacturer pages inspected 2026-10-27:

- [AMD Ryzen 7 9800X3D](https://www.amd.com/en/products/processors/desktops/ryzen/9000-series/amd-ryzen-7-9800x3d.html): AM5, DDR5, 8 cores/16 threads, 120 W TDP, Radeon graphics, no boxed cooler; distinct boxed and tray identifiers. Maximum package power and motherboard BIOS support are not established by those facts.
- [AMD Ryzen 7 9700X](https://www.amd.com/en/products/processors/desktops/ryzen/9000-series/amd-ryzen-7-9700x.html): AM5, DDR5, 8 cores/16 threads, 65 W TDP, Radeon graphics, no boxed cooler. Unknown prices must remain unknown.

These pages support CPU facts only. They do not prove a particular assembled configuration, board support, RAM clearance or PSU suitability. Additional real component sources are required before a fully verified real build can be shown.
