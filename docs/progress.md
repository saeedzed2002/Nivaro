# Implementation progress

Current status, 2026-10-27: **P01 verified; P02 in progress**. Catalog/domain/database foundation and provisional offline checks are implemented. Final backend dependency installation is blocked by confirmed lack of internet; catalog Docker runtime, generated frontend contracts and storefront integration remain unfinished. This is not completion of P02, the six-service store or all P00 backend checks. Earlier sections are chronological evidence, superseded where explicitly updated below.

## 2026-10-27 — P00/P01 in progress

The owner authorized implementation of the roadmap and required a generated image reference before each page is coded. See `design/PAGE_DESIGNS.md`. Earlier documentation-only restrictions describe previous turns and are superseded by this instruction; scope, private repository and live-provider restrictions remain.

- Repository: existing empty private `saeedzed2002/Nivaro`, confirmed by `gh repo view`. Identity: `saeedzed2002`, `saeedzed2002@gmail.com`.
- Host Node `24.20.0`; Docker engine `29.8.0`, initially no images or containers. No host upgrades.
- Official npm metadata confirms Next `16.4.3`, React `19.3.1`, pnpm `12.15.0`; Next requires Node >=20.9.0. Host Node satisfies this constraint. Container target remains `24.22.1-bookworm-slim`.
- Two bounded official Docker Hub pull attempts failed with TLS handshake timeout at the blob CDN. Stop repeated pulls; runtime/container/Compose Watch verification is not established.
- P01 builds the real bilingual storefront shell from the accepted home concepts. Listing/detail design references are prepared for the catalog slice. Research reference prices remain labeled, not sellable offers; conceptual hardware is labeled as illustration.
- Backend services and their execution probes are deferred to their dependency phases; P00 is not globally verified by a frontend build.
- Package-manager exception: pnpm `12.15.0` installed metadata successfully but its Windows npm shim did not execute; its direct native entry also rejected the documented network-bound flags. Select the already available pnpm `11.25.0`, pin it in the project and containers, and verify frozen installation. This is a tested-tooling exception, not a claim that it is the latest release.
- React installation exception: React DOM `19.3.1` requests stable `scheduler ^0.28.0`, but the registry returned stable `0.27.0` and only `0.28.0` prereleases. Keep prereleases excluded; test React/React DOM `19.2.4` together, whose metadata uses stable scheduler `^0.27.0`. Next's declared peer range accepts React 19.
- No live providers or public deployment.

## 2026-10-27 — Verified local storefront; P01 remains in progress

### Delivered

- Home, collection/search/category filtering, and product-detail reference templates, each recorded in the image-first register before implementation. Both locales and themes, local Vazirmatn/Inter fonts, responsive layout, separate language/market controls and persistent theme/market cookies.
- Five sourced reference products. Dates and source links are available in details. Missing market prices remain unverified, never invented or converted. Generic AI illustrations are explicitly labeled. No active selling, checkout, accounts, reviews, compatibility engine or saved-build persistence is claimed.
- Production standalone launcher, non-root Docker release, internal web service, loopback Caddy gateway, Compose Watch configuration, and private GitHub Actions workflow. The workflow checks the host build and then the container-served storefront; adding the workflow is not proof of a successful run.

### Verified baseline and checks

- Selected/tested frontend: host Node `24.20.0`, Next `16.4.3`, React/React DOM `19.2.4`, pnpm `11.25.0`, TypeScript `5.9.3`, ESLint `9.39.1`, Playwright `1.64.1`. ESLint 10 is outside current transitive plugin peer ranges; use 9 for this slice and review its deprecation when compatible plugins are available. Native `unrs-resolver` installation was explicitly allowed after inspecting its postinstall entry; no blanket install-script permission.
- Frozen/offline dependency installation and peer compatibility passed. Lint, TypeScript and production build passed. A Windows `EBUSY` rebuild was resolved by stopping this project's standalone server before rebuilding; no unrelated process was stopped.
- Production preview serves from `http://127.0.0.1:8080/fa` and `/en` using `node scripts/start.mjs`; no `next start`/standalone mismatch remains. This is a host process, not a container.
- Final browser run: **16 passed in 20.7 seconds**, installed Microsoft Edge via Playwright Chromium, no browser download. Twelve matrix cases cover 3 templates × 2 locales × 2 themes × 3 widths (`360`, `768`, `1440`), producing 36 page captures. Assertions cover direction/theme, visible header/search/main, visible image loading, no document overflow, no page errors or console errors. Behavioral cases cover URL filters, empty-result recovery, product navigation, market/language isolation and persistence, dialog Escape/focus return, saved theme and reduced motion.
- Compose base/development configuration validation passed. No local container build/run or Watch verification has passed. Registry TLS timeouts blocked earlier pulls; no further pulls were attempted in the latest continuation. Only `node:24.22.1-bookworm-slim` and `caddy:2.11.7` are requested for owner-assisted downloads. Optional explicit Arvan image variables are documented; specific mirrored tag availability is unverified.
- Evidence remains outside the repository under `C:/Users/S/.codex/visualizations/2026/10/26/01a179d7-c6c8-70b0-8191-257446c60022/nivaro-qa/`. Browser plugin was unavailable, so regular Playwright used the existing Edge executable. This is not Safari/Firefox, screen-reader, full accessibility or performance certification.

### Visual/interaction mismatch ledger

- Initial screenshots captured the header's empty streaming boundary and entry animation mid-frame. Removed the unnecessary header Suspense boundary; captures now wait for header/images/fonts and finish finite animations. Reviewed completed dark desktop home, English light desktop collection and Persian light mobile detail; image-led blue/RGB hierarchy, cards and responsive structure match the reference direction.
- Added the missing browser icon after console checks found its `404`. All matrix cases pass with console-error checks enabled.
- Dialog headings now have unique React IDs instead of potentially duplicated localized titles. Keyboard Escape and return to trigger pass; exhaustive focus/screen-reader review remains later QA work.
- Reference mockups contained invented commerce details. Real code intentionally uses only sourced fixtures, explicit inactive-feature dialogs, missing-price labels and no fake ratings or functional purchase claims.

### Remaining gates and handoff

- P01 is **not complete**: obtain the two images, stop the host preview before claiming port `8080` for Docker, run/review release containers and development Watch, record actual image digests and verify CI outcome.
- P00 frontend baseline is verified; Python/worker/checker and backend container baselines remain unverified and must precede their corresponding implementation. No six-service runtime readiness claim.
- P02 API-backed catalog, hardware compatibility and product comparison have not started. Remaining page references are pending in `design/PAGE_DESIGNS.md`; generate and inspect each before coding it. Cart, checkout, accounts, orders, admin and support remain later phases.
- Preserve the untracked Persian roadmap without reading or staging it. Its previously documented divergence remains intentional; use the English canonical document.

### Private Git and CI evidence

- Confirmed private destination and author identity immediately before commits. Preserved the initial documentation commit `149c52f`; added frontend `ef2c59d`, Docker/CI `be237bf`, and execution-status documentation `337320a`. Push of `main` through `337320a` succeeded.
- [CI run 40502820292](https://github.com/saeedzed2002/Nivaro/actions/runs/40502820292), revision `337320a0f17f67f492c368164f285e8a35471643`: installation, lint, TypeScript, production build, browser installation and host browser tests were confirmed successful. The last received state was container build/run in progress. Status monitoring and one retry then timed out connecting to GitHub; final container/CI outcome is **unknown**, not failed or passed. Re-read this run before deciding whether changes are needed.
- Local preview health returned `{"status":"ok","service":"web","dataMode":"reference-preview"}`. Docker image inventory was still empty at the final local check. No new local pull was attempted.

## 2026-10-27 — Owner-assisted full-stack download preparation

- Owner requested the complete planned download list in advance. Docker Hub metadata confirmed all six roadmap base tags plus optional `axllent/mailpit:v1.32.0` are active and provide `linux/amd64`. This does not establish mirror availability, successful pulls or backend compatibility.
- Added `scripts/Fetch-Images.ps1` (owner-operated sequential pulls, optional Mailpit, official-registry alternative, canonical local aliases, no automatic retries) and `docs/DOWNLOAD_PREPARATION.md` with the distinction between base images, application packages and offline build caches. No image download was started by the agent.
- Full offline readiness remains unverified: backend lockfiles/wheels, Linux frontend dependency cache, browser/system dependencies and a network-disabled build are separate work. Existing P01/P00 completion gates are unchanged.

## 2026-10-27 — Local P01 container and Watch gates verified

- Owner confirmed retaining Celery and supplied successful download output. Live local inspection confirms all seven planned `linux/amd64` base/tool images and canonical aliases. Transient Arvan timeout and Docker Hub DNS failures were followed by successful owner-assisted Arvan downloads; no further base-image pull was needed.
- Previous [CI run 40502820292](https://github.com/saeedzed2002/Nivaro/actions/runs/40502820292) is now verified **successful**, including host browser tests, container build/start and browser tests through the gateway. This supersedes the earlier unknown result, for revision `337320a` only.
- Local release image built and started behind Caddy at `http://127.0.0.1:8080`. Readiness is `200`, gateway returns `nosniff`, `/internal/test` returns `404`, and web runs as `uid=1000(node)`. Only web/gateway run; databases, brokers and workers have not been started.
- Docker-served browser matrix: **16 passed in 24.3 seconds**, both locales/themes and widths `360/768/1440`, including filter/product navigation, market/language behavior, dialog focus, reduced motion and console checks. Captures are under the existing external visualization directory in `nivaro-docker-qa/`; separately inspected `nivaro-docker-fa-dark.png` desktop and `nivaro-docker-en-light.png` mobile. Browser plugin remains unavailable; Playwright used installed Edge. No visual regression identified against the accepted baseline.
- Initial Watch test failed: host edits synchronized and compiled, but Next blocked the HMR origin `127.0.0.1` behind the proxy. Added only that hostname to development-only `allowedDevOrigins`, following the [official configuration reference](https://nextjs.org/docs/app/api-reference/config/next-config-js/allowedDevOrigins). No wildcard/CORS relaxation for production.
- Retest via `apps/web/scripts/verify-watch.mjs` **passed**: a temporary existing footer edit appeared in the same open browser document without reload; restoring the original source also appeared live. Source was restored byte-for-byte. Container ID, image and start time were unchanged before/after (`06de7d4a…`, development image `9132bf53…`). The script is included in CI's new development Watch gate.
- Node and Caddy defaults are pinned to actual repository digests. Separate release/development tags prevent switching modes from accidentally using a development image as the release. Lint, TypeScript and merged Compose configuration pass after these changes.
- `docker run --rm --pull never --network none ... nivaro-web:development` with frozen/offline installation and `pnpm build` passed. This is a rebuild inside the already populated Linux web image, not a network-free bootstrap. Changing dependency manifests may still require downloads; backend locks/wheels and backend runtime compatibility remain pending.
- P01 local acceptance gates are now satisfied. Final private push and CI for the new digest/Watch changes must still be recorded before marking the updated phase verified. P02 has not started; complete its Python/catalog baseline before introducing APIs, persistence or comparisons.
- Offline disposable-container binary probes confirm Python `3.13.18`, PostgreSQL `18.6`, Redis `8.10.3`, RabbitMQ `4.4.0` and Mailpit `1.32.0`. Mailpit uses `version --no-release-check`, not the generic `--version` flag. These version commands did not initialize persistent databases or start the full backend. Installed backend Python dependencies and cross-service behavior are still unverified.

### P01 final acceptance

- Changes committed as `2fa59af` (loopback HMR correction and regression check) and `42c9b3a` (pinned base images and separate development/release tags); private push succeeded.
- [CI run 40508570582](https://github.com/saeedzed2002/Nivaro/actions/runs/40508570582) for `42c9b3a50760d297c52730aaa662e900224feb63` **passed in 4m36s**: frozen installation, lint, types, production build, host browser tests, release containers, container browser tests, and development file synchronization/hot reload. Cleanup also passed.
- P01 is **verified**. Local runtime is left on `nivaro-web:release` behind pinned Caddy; only `127.0.0.1:8080` is published. Final readiness response is successful. Release image was rebuilt after the configuration correction; no temporary probe text remains.
- CI non-blocking maintenance notices: the pinned checkout/setup-node actions declare Node 20 and were forced onto the runner's Node 24; `ubuntu-latest` is undergoing a platform migration. Current run passed, but update/test the action runtime pins and consider an explicit runner image during CI maintenance. These are distinct from the project's selected Node 24 runtime.
- Next stage remains P02: resolve/test the backend dependency baseline, implement the catalog database/API and connect existing reference pages. Product comparison needs its own generated/inspected image before implementation. Celery remains the selected task runner for its later job-processing phase; no extra task-runner service has been added.

## 2026-10-27 — P02 catalog foundation; internet-dependent gates remain open

The owner instructed continuation and then explicitly confirmed that internet access is currently unavailable. Stop package download attempts; continue independent local work. This section supersedes the earlier statement that P02 has not started.

### Delivered and locally checked

- Generated and inspected dedicated product-comparison and PC-builder page references; copied them to `design/pages/` and registered them before any new page implementation. Builder reference includes a light mobile inset. Corrected the design brief's unconditional GPU assumption and rejected generated prices/specifications as evidence. Page implementations are still pending.
- Added only the catalog service foundation: typed settings and secret-file credentials, async database lifecycle, liveness/readiness, bounded public read APIs for categories/products/variants, same-category product comparison and stateless build evaluation. Search normalizes Persian yeh/kaf/ZWNJ/whitespace and uses literal token-prefix indexes. Price filtering stays within one market; rating sort is rejected until P08 reviews exist.
- Added typed specifications, separate tray/boxed variants, integer IRR/USD offers, conservative compatibility rules, revision fingerprints, explicit unknown/incomplete/conflict findings, core/peripheral research subtotals and aggregate repeated-SKU availability. No browser-supplied compatibility claim is trusted. Evaluation does not reserve stock. Virtual templates have no parent offer/stock counter; finished prebuilts use only their own physical SKU.
- Added independent `nivaro_catalog` database/role on the existing PostgreSQL 18.6 Linux image, using the new optional `compose.catalog.yaml` overlay and fresh `nivaro_catalog_postgres` volume. No existing volume was deleted. Role tests confirm no superuser, role-creation, database-creation or replication privileges. Cross-service database isolation will need its P03 counterpart when that database exists.
- Applied migrations from the initially empty database through `0002_revision_guards`; `alembic check` reports no new upgrade operations. Constraints enforce stock, independent currency, exact toman amounts, uniqueness, specification kind and two-level categories. Triggers reject technical/offer edits without a newer revision. The insert-only seed was rerun without duplicating or overwriting records: **6 products, 7 variants, 6 reference observations**. All seeded stock remains unverified and offers unavailable for sale.
- Final provisional test run: **66 passed in 2.01 seconds**. Coverage includes real PostgreSQL/API reads, seeded packaging separation, Persian filtering/index eligibility, same-market price filters, private/docs route denial, sanitized unavailable responses, chunked-body limit, stale spec/rule evidence, GPU/PSU/air-cooler/storage checks, unknown facts, money constraints and idempotent seed. Integration fixtures are rolled back. Database changes were observed through the API, **not yet through the storefront**.
- Ruff lint passed; formatting applied. Two diagnostic OpenAPI exports have identical hashes; they remain in ignored `work/`, not canonical release contracts. Existing storefront readiness still reports `reference-preview` and stays healthy at loopback port 8080.

### Exact validation limits

- Selected backend pins remain the roadmap's Python 3.13.18 and listed dependency versions. A bounded `pip install uv==0.13.5` attempt inside the existing Python image timed out on PyPI; a short official metadata request also timed out. The owner then confirmed no internet. No further network download or Docker base-image pull was attempted.
- Existing cache metadata was inspected, but an explicitly offline isolated-environment probe lacked required cached wheel contents and failed without installing a substitute stack. No host/global package was upgraded or replaced.
- Provisional checks instead used already installed **Windows Python 3.12.3**, FastAPI **0.115.0**, Pydantic **2.9.2**, pydantic-settings **2.5.2**, SQLAlchemy **2.0.35**, Alembic **1.13.2**, psycopg/binary **3.3.4**, HTTPX **0.27.2**, pytest **9.1.1**, pytest-asyncio **0.24.0**, Ruff **0.16.3**. These are test-environment observations, **not an approved replacement for the selected runtime**. Mypy was unavailable; strict type checking has not passed. The supplemental Hatchling pin must also be verified during final resolution.
- No backend `uv.lock`, frozen install, non-root backend image, one-shot container migration job, final OpenAPI/types generation, frontend API integration or P02 browser/CI acceptance has passed. No catalog API has been routed through the running gateway. P02 remains **in progress**, blocked at its final dependency/runtime gate rather than complete.
- Liquid/radiator layouts deliberately remain `needs_review`; no fabricated full-build compatibility or benchmark is advertised. Additional source-backed component data is required to demonstrate a complete real system. Synthetic tests are not retail fixtures.
- The temporary loopback PostgreSQL test port was removed after checks by recreating only its container with the same volume. Final database container is healthy with **no host-published port**. Web/gateway remain the verified P01 release. Local secrets and diagnostic files are ignored; the Persian roadmap was not read or edited.

### Next continuation

Restore package access, resolve/freeze and test the selected Linux dependency baseline, then finish catalog image/migration integration and generated frontend contracts. Implement the already pictured comparison/builder pages and connect the existing home/list/detail pages, preserving explicit unavailable/error states. Complete real-source fixtures, responsive/browser checks and private CI before marking P02 verified. See `services/catalog/README.md` for commands and boundaries. No additional base image is currently needed; Python packages and contract-tool dependencies are the missing downloads.

### Local Git checkpoint

- Rechecked local origin (`https://github.com/saeedzed2002/Nivaro.git`) and author (`saeedzed2002`, `saeedzed2002@gmail.com`) before committing; preserved the existing repository and history.
- Local commits: `acc3730` (comparison/builder image references), `a3ca2d2` (typed hardware and compatibility policies), `93010bd` (PostgreSQL/schema/read APIs and provisional verification evidence). Each staged diff passed whitespace checks. Secrets, diagnostic exports and the Persian roadmap were excluded.
- No push or new CI run was attempted after the owner confirmed internet is unavailable. These P02 commits are local only; the successful P01 CI run is not evidence for this new backend code.
