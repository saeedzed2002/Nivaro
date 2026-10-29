# P04 administration reference provenance — 2026-10-28

Built-in image generation with inspected local Blue RGB home and account-profile references. Existing brand selection is retained; these are implementation references, not another style-selection round. Each page uses a dark Persian RTL desktop composition and a separate light mobile inset. English/LTR and other theme/viewport combinations still require implementation review. No page code was added before generating these images.

| Workspace reference | Generated original | Recorded page-specific brief |
| --- | --- | --- |
| `pages/admin-products.png` | `exec-c0d8459b-7dbe-4602-ac22-6d21e749da01.png` | Staff products list, restrained branded header, store/language/theme access, right navigation, search/category/publication filters, table with product/category/variant count/publication/media state/edit, mobile cards and pagination. No commerce metrics, shopping cart or invented prices. |
| `pages/admin-product-editor.png` | `exec-3471d139-e965-41ee-a4d2-ed5612dda123.png` | Same staff shell, draft-save distinct from gated publish, basic/variants/prices/images tabs, gallery with ready/processing/failed items, upload file button, retry, alt text, reorder controls, license/source field, independent market price context, preserve previous active image during replacement. |

Original outputs are retained under `C:/Users/S/.codex/generated_images/01a179d7-c6c8-70b0-8191-257446c60022/`. Copies live in this project. Concept art is not exact-SKU photography or permission to invent product facts, counts, offers or availability.

## Inspection and corrections before coding

- Products: preserve the calm blue hierarchy and mobile card adaptation. Sample counts/models and the illustrated published/ready statuses are not actual database values. Use existing category symbols for products lacking accurate licensed media. Keep status text, not color-only indicators; expose actions according to server permissions. Generated sidebar links must not lead to unimplemented pages.
- Editor: retain clear pending/failed image actions and previous-image preservation. The generated format label accidentally repeats WebP and omits JPEG: correct it to JPEG, PNG, WebP and express size as 8 MiB. Gallery examples mix case/GPU/RAM images; actual gallery images must belong to the edited product/variant. The preview shows a ready main image while readiness still reports a missing valid image: real UI must derive consistent readiness from server state. Never infer it from the concept illustration.
- Use keyboard-accessible reorder actions, correctly labeled file selection, explicit save feedback and stale-edit conflict recovery. A failed job's retry must follow safe backend rules; invalid content must be replaced rather than endlessly retried. Do not reveal private failed originals via public media routes. No speculative RGB animations on form controls; short focus/transition feedback must respect reduced motion.
- Categories and a distinct staff-profile/avatar page still need their own images before page implementation. The existing customer-profile reference supports its avatar extension, with processing/failure states to verify separately.

## Categories continuation — 2026-10-29

Built-in `imagegen` output copied into `pages/admin-categories.png` and inspected. Original filename: `exec-080a227f-2606-4f15-b9f7-3e60e4398c6a.png` in the same generated-images directory above.

Final generation brief: high-fidelity NIVARO GAMING staff category management reference board with a large Persian RTL dark desktop and narrow light mobile view. Near-black `#090d15`, panels `#111a29`, white light mode, electric blue `#2864ff`, small cyan/indigo/RGB brand accents, Vazirmatn/Inter typography; no green-dominant design or sales metrics. Staff header with language/theme/storefront access and sidebar products/categories/session/logout. Title «دسته‌بندی‌ها», two-level hierarchy subtitle, search/count/add category action. Tree table with root and indented child categories, slug, parent, actual product-count position and edit control; mobile stacked rows. Adjacent selected-category editor with Persian name, English name, URL slug, eligible top-level parent selector, two-level help, save/discard and explicit conflict reload. No delete, raw JSON, prices or uploads. Product names/counts are illustrative. Preserve existing references and brand rather than introducing a redesign.

Inspection corrections: use actual counts (the image's count does not match all illustrated rows); retain the implemented Nivaro logo; omit generated decorative slogans. The banner's generated text is not a reliable conflict policy: actual version conflicts preserve local input until explicit replacement. Tree/list indentation must preserve keyboard and screen-reader labels, and server validation must enforce depth/cycle/version rules.
