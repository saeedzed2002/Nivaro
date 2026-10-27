# Image-first implementation register

Owner instruction, 2026-10-27: create an image for every page before implementing it, then build that page from the image. Coding is authorized; extra approval of every generated reference is not required. Maintain the accepted Blue RGB identity, both themes and both languages. No new route may skip this gate. One dynamic template covers its product/order IDs; materially different screens need separate references.

## Implemented visual slices

| Page | Image produced before code | Status |
| --- | --- | --- |
| Home | [Dark](concepts/r2-blue-rgb-fa-dark.png), [light](concepts/r2-blue-rgb-fa-light.png) | P01 implemented; local container/browser/Watch and private CI verified |
| Products / category / search results | [Products](pages/products.png) | Generated and inspected before coding; reference-only collection for P01, API integration in P02 |
| Product details, including reviews section | [Details](pages/product-details.png) | Generated and inspected before coding; no fabricated review counts or live purchase action |
| Product comparison | [Comparison](pages/product-comparison.png) | Generated and inspected 2026-10-27, before page code; API-backed implementation in P02 checkpoint |
| PC builder | [Workspace](pages/build-workspace.png) | Generated and inspected 2026-10-27, before page code; dark desktop/light mobile reference; temporary selection/evaluation UI implemented |

## Design plan applied

- Palette: ink `#080A10`, charcoal `#111722`, royal blue `#2563EB`, sky accent `#72B6FF`, white `#FFFFFF`, light separation `#F7F9FC`. RGB colors belong to hardware lighting; readable controls retain blue identity.
- Typography: local Vazirmatn for Persian, local Inter for Latin body/display; bold display heading, restrained spaced English captions, tabular monetary values. No remote font runtime requests.
- Home composition: full-width hardware studio with typography opposite the PC; category strip; reference cards; dedicated keyboard showcase; assembly workbench introduction. Keep commerce surfaces quiet. The signature is a hardware workspace, not an unrelated generic neon dashboard.
- Listing: scoped photo banner, breadcrumb and collection heading, filter sidebar, image-first cards. On mobile, filters precede results and remain ordinary labeled controls.
- Detail: large honest illustration, specific model and reference offer, recorded facts and review availability below. Never convert generated text/specifications into product data.
- Motion: short transform/focus feedback, no rotating carousel, no animated prices; respect reduced motion.
- Concept review corrections: listing mockup invented extra models/prices and combined some settings. Implementation uses only documented research data and separate language/market/theme decisions. Detail mockup's generated technical table is not a source; only recorded source-backed facts are used.
- Dark/light hero photos are original built-in image generation assets; source PNGs in `assets/`, compressed WebP derivatives in `apps/web/public/images/`. No competitor photos are shipped. Generic product illustrations are visibly labeled and must be replaced by accurate licensed SKU media before real sales.

## Remaining page gates — do not implement until the image exists

| Page/template | Phase | Image status |
| --- | --- | --- |
| PC builder | P02/P05 | Reference completed above; durable saved builds remain P05 |
| Saved builds | P05 | Pending |
| Product comparison | P02 | Reference completed above |
| System comparison | P05 | Pending |
| Gaming PCs landing | P02 | Pending; current nav opens the pictured products template with PC filter |
| Guides | P10 | Pending |
| Cart | P05 | Pending |
| Checkout | P06 | Pending |
| Payment result / pending / failure | P07 | Pending |
| Customer login / OTP | P03 | Pending |
| Account overview | P03 | Pending |
| Profile / avatar | P03/P04 | Pending |
| Addresses | P03 | Pending |
| Order history | P07 | Pending |
| Order detail / timeline | P07 | Pending |
| Customer support | P09 | Pending |
| Administrator login | P03 | Pending |
| Administrator dashboard | P10 | Pending |
| Administrator products | P04 | Pending |
| Product editor / images | P04 | Pending |
| Review moderation | P08 | Pending |
| Administrator orders | P07 | Pending |
| Administrator order detail | P07 | Pending |
| Payments / reconciliation | P07 | Pending |
| Users / permissions | P10 | Pending |
| Support inbox | P09 | Pending |

Record reference creation and inspection before starting each template. Carry empty, loading, error, keyboard, mobile and localized variations into implementation QA. Dialogs explaining inactive P01 features do not pretend to implement those pages.

### P02 reference inspection

- Comparison: two product columns, sticky specification labels, same-category selection and differences toggle. Correct the generated mockup's false emphasis on identical core counts, invented dates/prices, and generic CPU packaging. Unknown facts render as unknown, never zero; no overall winner.
- Builder: readable component rows, a sticky price/evaluation summary, optional peripherals separated below and a light mobile layout. Correct the mockup's unconditional dedicated-GPU requirement: it depends on CPU graphics and the requested workflow. Generated cache counts and external guide labels are not technical evidence. No durable save, physical assembly service or payable total is promised by P02.
- Both references preserve the approved blue/RGB system. Their images are layout references, not exact-SKU photographs, verified facts, accessibility checks or functioning animations.

Prompts and provenance: [Implementation prompts](IMPLEMENTATION_IMAGE_PROMPTS.md). Static image approval is not runtime verification; see [progress](../progress.md).
