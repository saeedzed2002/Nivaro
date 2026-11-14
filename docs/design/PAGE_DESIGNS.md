# Image-first implementation register

Owner instruction, 2026-10-27: create an image for every page before implementing it, then build that page from the image. Coding is authorized; extra approval of every generated reference is not required. Maintain the accepted Blue RGB identity, both themes and both languages. No new route may skip this gate. One dynamic template covers its product/order IDs; materially different screens need separate references.

## Implemented visual slices

| Page | Image produced before code | Status |
| --- | --- | --- |
| Home | [Dark](concepts/r2-blue-rgb-fa-dark.png), [light](concepts/r2-blue-rgb-fa-light.png) | P01 implemented; local container/browser/Watch and private CI verified |
| Products / category / search results | [Products](pages/products.png) | Generated and inspected before coding; reference-only collection for P01, API integration in P02 |
| Product details, including reviews section | [Details](pages/product-details.png) | Generated and inspected before coding; no fabricated review counts or live purchase action |
| Product comparison | [Comparison](pages/product-comparison.png) | Generated and inspected 2026-10-27, before page code; API-backed implementation verified in P02 |
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
| Saved builds | P05 | [Reference](pages/saved-builds.png), generated and inspected before implementation |
| Product comparison | P02 | Reference completed above |
| System comparison | P05 | [Reference](pages/system-comparison.png), generated and inspected before implementation |
| Gaming PCs landing | P02 | Pending; current nav opens the pictured products template with PC filter |
| Guides | P10 | Pending |
| Cart | P05 | Pending |
| Checkout | P06 | Pending |
| Payment result / pending / failure | P07 | Pending |
| Customer login / OTP | P03 | [Login](pages/customer-login.png), generated/inspected 2026-10-28; implemented and locally verified |
| Account overview | P03 | [Overview](pages/account-overview.png), generated/inspected 2026-10-28; implemented and locally verified |
| Profile / avatar | P03/P04 | [Profile](pages/account-profile.png), generated/inspected 2026-10-28; profile locally verified, processed avatar remains P04 |
| Addresses | P03 | [Addresses](pages/account-addresses.png), generated/inspected 2026-10-28; implemented and locally verified |
| Order history | P07 | Pending |
| Order detail / timeline | P07 | Pending |
| Customer support | P09 | Pending |
| Administrator login | P03 | [Admin login](pages/admin-login.png), generated/inspected 2026-10-28; implemented and locally verified |
| Administrator dashboard | P10 | Pending |
| Administrator products | P04 | [Products](pages/admin-products.png), generated/inspected 2026-10-28; list/search/filter/pagination implementation added 2026-10-29, verification below |
| Administrator categories | P04 | [Categories](pages/admin-categories.png), generated/inspected 2026-10-29 before implementation; two-level hierarchy, bilingual form, parent constraints and responsive list |
| Product editor / images | P04 | [Editor](pages/admin-product-editor.png), generated/inspected 2026-10-28; basic content/status/stock/history implementation added 2026-10-29; gallery, variant and price forms remain pending |
| Review moderation | P08 | Pending |
| Administrator orders | P07 | Pending |
| Administrator order detail | P07 | Pending |
| Payments / reconciliation | P07 | Pending |
| Users / permissions | P10 | Pending |
| Administrator profile / avatar | P04 | [Staff profile](pages/admin-profile.png), generated and inspected 2026-11-07 before implementation; own avatar/name, read-only staff email/role, dark desktop and light mobile |
| Support inbox | P09 | Pending |

Record reference creation and inspection before starting each template. Carry empty, loading, error, keyboard, mobile and localized variations into implementation QA. Dialogs explaining inactive P01 features do not pretend to implement those pages.

### P02 reference inspection

- Comparison: two product columns, sticky specification labels, same-category selection and differences toggle. Correct the generated mockup's false emphasis on identical core counts, invented dates/prices, and generic CPU packaging. Unknown facts render as unknown, never zero; no overall winner.
- Builder: readable component rows, a sticky price/evaluation summary, optional peripherals separated below and a light mobile layout. Correct the mockup's unconditional dedicated-GPU requirement: it depends on CPU graphics and the requested workflow. Generated cache counts and external guide labels are not technical evidence. No durable save, physical assembly service or payable total is promised by P02.
- Both references preserve the approved blue/RGB system. Their images are layout references, not exact-SKU photographs, verified facts, accessibility checks or functioning animations.

Prompts and provenance: [Implementation prompts](IMPLEMENTATION_IMAGE_PROMPTS.md). Static image approval is not runtime verification; see [progress](../progress.md).

### P02 runtime acceptance — 2026-10-28

The five implemented templates passed the responsive browser matrix in Persian/English, dark/light and 360/768/1440 widths, plus interaction/error checks. Actual database edits appeared in the storefront, and catalog outage/recovery was verified. Private CI for `abd42b3` passed clean release builds, backend/contract checks, host/container browser suites and development Watch. Representative visual review covered the desktop builder, complete-build findings and Persian light mobile comparison. Unknown-only totals show a dash; longer compatibility findings remain ordinary scrollable content. These results validate the delivered slice, not pending pages or live commerce. Exact evidence is in the progress log.

### P03 reference inspection — 2026-10-28

All five images above were generated and visually inspected before any identity page code. Each combines a dark Persian desktop and a light mobile state; English/LTR and remaining viewport variants must be verified in implementation, not inferred from the image.

Generation briefs and output provenance: [P03 identity references](P03_IDENTITY_IMAGE_PROMPTS.md).

- Customer login: retain the split hardware/form composition, clear phone field, country context, resend state and explicit local-mock disclosure. Correct the generated claim that an actual SMS was sent. Use one accessible OTP input with paste/autocomplete support rather than six independently focused inputs shown in the image. Test numbers are development-only; do not reuse the generated phone number as an approved fixture.
- Overview: retain sidebar, profile/address shortcuts, hardware banner and session safety action. No invented order/saved-build/reward counts. All-device logout includes the current device; correct the generated dialog's contradictory exception.
- Profile: retain name editor, read-only verified number and explicit save feedback. Use actual user data, not the generated person's name. Omit generated orders/favorites/support links until those flows exist. Avatar processing remains P04; no pretend upload or unimplemented phone-change support promise.
- Addresses: retain empty state and clear add/edit form; generated country/city menus and ten-digit postal rule are not universal address policy. Use country-aware fields without implying enabled international fulfillment. Show validation after interaction, not an initially all-red form. Confirm deletion, enforce ownership server-side and avoid unsupported extra navigation.
- Admin login: retain the separate restrained credential panel, generic error, show-password control and storefront link. Generated email/hidden password are placeholders, never bootstrap credentials. Omit shopping cart navigation on this staff authentication screen.
- Keep the existing Nivaro wordmark/header components; small logo variations in generated images do not authorize a rebrand. No speculative social links or nonexistent legal/support pages are introduced by these mockups. References provide layout, not tested accessibility, animations, working authentication or an English-language review.

### P03 runtime review — 2026-10-28

Five references were implemented before browser verification, preserving the established header/wordmark, blue accents, RGB hardware and both themes. Existing generated showroom artwork is reused for the login split scene and overview banner; it is decorative, not a new product photograph. Staff login is a restrained separate form without shopping controls; its signed-in state shows only server-validated permissions, with no invented operational dashboard.

The isolated browser suite passed 15 tests, including 60 page/locale/theme/viewport captures at 360/768/1440 widths, image readiness and no page errors or horizontal overflow. Visual inspection covered dark Persian desktop login/overview, English light mobile profile, Persian light mobile empty addresses and English dark staff login. Corrected implicit field names that included helper text, increased identity body-copy size, and removed inherited excessive field margins. Image readiness is awaited before capture; an earlier overview capture preceded lazy-image completion and is not the final visual evidence.

Evidence directory: `C:/Users/S/.codex/visualizations/2026/10/26/01a179d7-c6c8-70b0-8191-257446c60022/nivaro-p03-visual-final/`. Real local flows cover OTP, profile persistence, address CRUD, two-tab session recovery, customer/staff separation, role-change visibility and logout. An injected unavailable response preserves the profile draft. This is not an actual network-outage test or a full assistive-technology audit. Processed avatar, order history and operational administrator pages remain later gates.

### P04 initial staff UI — 2026-10-29

Reinspected both registered products/editor references before coding. Retained the existing blue/RGB brand and local fonts, restrained staff header/sidebar, outlined edit actions, publication labels, desktop table/mobile cards, tabbed editor and readiness side panel. Reused existing truthful category artwork/symbols rather than generating inaccurate model photographs. Both themes use existing tokens; no redesign or new dependency.

Implemented list/search/category/status/pagination and create/edit content, publication transitions, stock adjustment with explicit confirmation, and audit history. Readiness is server-owned; missing media prevents publishing a new draft. The generated reference's gallery tab is not implemented yet: show a clear unavailable explanation rather than fake upload/progress controls. Category/profile sidebar links are omitted until their own references and working pages exist. Variant metadata and market-price forms remain later work; the backend contracts already exist.

Initial visual inspection covered Persian dark desktop list and English light mobile editor. The interface preserves content after a conflict and displays current/local fields side by side, requiring explicit replacement rather than silently rebasing. Corrected the slug's accessible name to exclude helper text. Full-page test captures scroll through lazy thumbnails before checking loaded images. Final browser evidence/results belong in the progress log; a reference or screenshot alone is not accessibility or functional acceptance.

Final local run: 16 identity/staff browser tests passed, including 24 new staff list/editor captures across both languages/themes and 360/768/1440 widths. Also inspected Persian dark desktop editor and Persian light mobile list; aligned paired input fields without stretching. Confirmed actual create/edit/conflict/stock/history/status journeys against a disposable database, plus existing permission and service-outage behavior. Evidence: `nivaro-p04-staff-ui/` in the existing visualization root; see the progress log for exact scope and remaining P04 work.

### P04 editor continuation — 2026-10-29

Reinspected `pages/admin-product-editor.png` before extending its existing models/specifications and market-price sections. Retain its tabbed panel, restrained blue borders, responsive field columns and explicit readiness. Technical facts use labeled fields with unknown states and source rows; no raw JSON editor. Each market has a separately selected price form, showing whole tomans for Iran and dollars/cents internationally regardless of UI language. Never derive one market's price from the other. Existing editor reference covers this page extension; no new page or visual rebrand is introduced. New category pages still require their own generated reference.

### P04 categories reference — 2026-10-29

Generated with the built-in image tool and visually inspected before page implementation. Workspace asset: `pages/admin-categories.png`; original: `C:/Users/S/.codex/generated_images/01a179d7-c6c8-70b0-8191-257446c60022/exec-080a227f-2606-4f15-b9f7-3e60e4398c6a.png`. Prompt and corrections are recorded in `P04_ADMIN_IMAGE_PROMPTS.md`. Retain the two-level tree/list, adjacent bilingual edit form, eligible-parent selector, blue staff navigation and light mobile treatment. Generated names/counts are fixtures, not database evidence. Preserve the existing wordmark rather than the generated logo variation; remove decorative sidebar slogans. Show conflict guidance only on an actual conflict; the generated generic reload banner must not discard drafts implicitly. Do not add deletion, arbitrary image URLs or nonfunctional controls.

### P04 category implementation review — 2026-11-07

Implemented the registered category reference with live counts, a two-level list and bilingual edit panel. Actual conflicts preserve local input and require explicit replacement. Reviewed Persian dark desktop and light mobile screenshots; moved the mobile edit panel before the long list. No horizontal overflow or page errors across both locales/themes and 360/768/1440 widths. Evidence: `nivaro-p04-categories-mobile/` under the existing visualization root. Generated mockup data was never copied into the owner's database.

### P04 product gallery — 2026-11-07

Reinspected `pages/admin-product-editor.png` before extending its Images tab. Retained the blue outlined gallery tiles, selected/cover indicators, ready/queued/processing/failed text, upload area, bilingual alternative text, explicit image classification and previous-image preservation. Existing product-detail reference covers its public gallery thumbnails. Keyboard buttons select images and promote the selected ready image to cover; a confirmed removal clears references without deleting storage inline. The file control remains native and accessible. Do not copy the generated reference's incorrect repeated format label or arbitrary mixed-product images.

The real upload/replacement/conflict/cover/removal journey passed in a disposable stack. Captured staff and public gallery in both locales/themes at 360/768/1440 pixels. Reviewed dark Persian desktop, light Persian mobile and English light mobile product detail. Corrected the upload area from a squeezed horizontal row to the reference's stacked layout. The native file picker uses the browser's language, while its label/help/errors use the selected site language. Minor RGB accents remain on artwork; motion is limited to processing feedback and respects reduced motion. No new image-generation gate is needed for these existing templates. Full-suite evidence and runtime state are recorded in `docs/progress.md`.

### P04 staff profile reference — 2026-11-07

Generated and inspected `pages/admin-profile.png` after the catalog-media checkpoint, before staff-profile page code. Retain the restrained staff shell, editable own display name, non-editable email/role, avatar with bounded upload help, processing indicator and old-image preservation, plus the stacked light mobile layout. The bottom failure panel is a separate state example, not a simultaneous state to show beside processing. Only show removal when an active avatar exists; a monogram is not a stored avatar. Correct size wording to 8 MiB, expose clear accessible statuses, use actual identity data and preserve the implemented brand/navigation. Do not create the placeholder email/account, infer role-edit authority, add unimplemented password/phone actions or make generic processing failure sound like proof the user's file is invalid. Customer profile's existing reference covers its own avatar extension. Generation provenance is in `P04_ADMIN_IMAGE_PROMPTS.md`; runtime acceptance remains pending.

### P04 staff profile runtime — 2026-11-11

Implemented from the registered reference and inspected Persian dark desktop and English light mobile captures after the complete 20-journey browser suite passed. Image selection is localized and keyboard accessible. Active images load through authenticated private identity routes. Processed replacement, failed replacement preservation and removal were exercised for customer and staff scopes. Evidence lives in `nivaro-p04-phase-final/` outside the repository.

### P05 cart reference — 2026-11-11

Generated and inspected `pages/cart.png` before cart UI implementation. Retain the Blue RGB dark desktop/light mobile visual system, grouped component rows, standalone lines, explicit missing-price and availability states, estimated subtotal and non-reservation notice. The image is illustrative. Correct its complete-build label: compatibility mode does not promise physical assembly or delivery service. Use the same SKU in multiple systems/spare rows when demonstrating grouping. Empty cart is a separate state, never simultaneously shown below a populated cart. Calculate badge counts from actual lines/quantities, use actual catalog data, and do not present the reference's two-item badge as a requirement. Shipping/tax remain pending until authoritative checkout exists. Page implementation and runtime acceptance are pending.

### P05 cart storefront implementation

The cart template implements grouped and standalone rows, a separate estimated summary and explicit empty/unavailable states. Inspected Edge captures for dark English desktop and light Persian mobile. Browser fixtures supplied synthetic cart items to verify conflict recovery, removal, independent markets and responsive layout. See the progress log for the separate real gateway/session checks and outstanding build/group screens.

### P05 saved builds and system comparison references

The generated desktop dark and mobile light references are inspected and registered before page implementation. Keep the storefront header and existing market terminology. Saved-build cards use the draft name, mode and real actions; omit mock component counts and exact system imagery. Comparison uses two summary columns, clear slot differences and missing-value dashes. Compatibility and pricing come from catalog, and neither system is marked as the winner.
