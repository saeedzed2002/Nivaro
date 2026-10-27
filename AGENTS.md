# Nivaro Gaming Agent Instructions

## Canonical project specification

- Read `docs/NIVARO_ROADMAP_EN.md` before architecture, planning, implementation, or project review. It is the authoritative English specification.
- `docs/NIVARO_ROADMAP.md` is a non-authoritative Persian reading copy for the human owner. Do not open, edit, or use it as implementation input unless the user explicitly requests translation or editing of that copy.
- If the copies diverge, follow the English specification and report the discrepancy. Do not merge conflicting requirements from the Persian copy.
- Keep future implementation handoffs and specification references pointed at `docs/NIVARO_ROADMAP_EN.md`.
- The owner revised the product brief on `2026-10-27`: gaming hardware and equipment, PC assembly, product/system comparison, Persian (`fa-IR`, `RTL`) and English (`en`, `LTR`), and light/dark themes.
- The owner explicitly selected independent international USD pricing and sales, not a converted display of Iranian prices. Follow the English roadmap's market/currency rules and unresolved live-market prerequisites.
- `docs/design/GAMING_DESIGN_RESEARCH.md` records research, reference prices, accepted visual baseline and mockup limitations. It supplements the roadmap and does not itself authorize implementation.
- Accepted visual baseline: `docs/design/concepts/r2-blue-rgb-fa-dark.png` and `docs/design/concepts/r2-blue-rgb-fa-light.png`. Blue is the primary brand spectrum on black/dark and white/light backgrounds; retain multicolor RGB lighting including red, purple, indigo and green. The green-dominant concept is rejected, not green as a minor RGB/status color. Refine exact tokens, accessibility and responsive layouts during implementation; do not restart overall style selection. Both themes are required.
- Roadmap revision `1.3.0` finalizes the owner's delegated assembly decisions: six services; stable configuration groups/line IDs through cart and order snapshots; revision-bound compatibility/quotes; component-derived inventory for virtual builds versus finished-SKU inventory for stocked prebuilts. Read `ADR-014` through `ADR-017` and the detailed assembly contracts before implementing them. Do not reopen these decisions without concrete contradictory evidence or new owner feedback.

## Execution boundary

- On `2026-10-27` the owner explicitly authorized implementation of the roadmap. Proceed sequentially through its phases, including project dependencies, local execution and the documented private Git workflow. Do not infer permission for public deployment, real payments/SMS, purchases, data deletion or repository publication.
- Image-first rule: before implementing each page, generate and inspect its own image reference, record it in `docs/design/PAGE_DESIGNS.md`, then implement from it. The existing accepted Blue RGB pair satisfies this gate for the home page. Use the same visual system for subsequent pages and both themes. Images do not establish tested accessibility, responsive behavior, working animations, verified product specifications or prices.
- Docker Desktop is running. Check existing images first; bound pull attempts and do not spend prolonged time retrying blocked downloads. If registry access fails, continue independent implementation/local checks and report Docker verification as incomplete until it actually passes.
- Working display brand: `Nivaro Gaming`. Keep `D:\Project\Nivaro`, the canonical roadmap filenames, and the existing private repository identity unless a deliberate rename is separately selected; naming freedom does not require a rename.
- The explicit start instruction has been received. Follow the English specification's phase dependencies, Git, Docker, verification, and privacy rules; keep evidence and unfinished phases in `docs/progress.md`.
- Preserve existing files, repository history, and the private GitHub repository. Do not recreate or publish the repository.

## Communication

- Treat the owner as an experienced software developer. Be direct, factual, and specific.
- When communicating in Persian, preserve clear RTL reading order and wrap English terms, identifiers, numbers, paths, commands, URLs, and versions in inline code. Use code blocks for actual code/configuration/commands only.
