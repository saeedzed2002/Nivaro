# Nivaro Gaming

Bilingual Persian/English gaming hardware storefront, following [the canonical roadmap](docs/NIVARO_ROADMAP_EN.md). Blue-led dark and light themes. Private single-vendor project; preserve the existing repository.

## Current delivery

P01 storefront implementation: home, reference product collection, URL-based filters/search, and reference product details. Pages are built from generated references recorded in [the image-first register](docs/design/PAGE_DESIGNS.md). Full six-service commerce implementation is still pending. No purchase, login, stock guarantee, saved-build persistence or payment is simulated as completed by this frontend.

Reference prices have retailer sources, dates, market and packaging metadata. Iran and international prices are independent. Changing language preserves the selected market. Images are conceptual illustrations, not exact SKU photos.

P02 catalog foundation is now implemented separately: independent PostgreSQL schema/role, repeatable research seed, read-only catalog APIs, typed specifications, product comparison and versioned compatibility evaluation. Owner-assisted dependency installation and checks with the selected Linux versions now pass against real PostgreSQL. Dedicated backend application-image execution, generated frontend contracts and API-to-storefront integration remain pending. See [catalog status and continuation](services/catalog/README.md) and [progress](docs/progress.md). This does not change the running P01 storefront into an API-backed store yet.

## Local development

Requires Node 24 and pnpm 11.25.0. The project pins pnpm and direct dependencies; do not force peer dependencies.

```powershell
cd apps/web
pnpm install --frozen-lockfile
pnpm dev --port 8080
```

Open `http://localhost:8080/fa` or `http://localhost:8080/en`. This fallback runs on the host, not in Docker. See [progress](docs/progress.md) for actual verification evidence and container limitations.

## Docker development

```powershell
docker compose -f compose.yaml -f compose.dev.yaml up --build --watch
```

The gateway binds only to `127.0.0.1:8080`; web is internal. Source/public assets sync via Compose Watch, dependency manifests trigger rebuild. Windows node_modules never enter Linux containers. Do not remove volumes or prune the user's Docker environment.

```powershell
docker compose up -d --build
docker compose ps
```

Base Compose builds a non-root standalone web release. Release and development images have distinct local tags (`nivaro-web:release` and `nivaro-web:development`). The Node/Caddy defaults are pinned to the verified downloaded digests. Both local Docker release execution and Compose Watch were verified on 2026-10-27; see [progress](docs/progress.md). Initial registry/package access is still needed on a clean machine. For the complete owner-assisted base-image list, see [download preparation](docs/DOWNLOAD_PREPARATION.md).

Only two base images are needed for this phase: `node:24.22.1-bookworm-slim` and `caddy:2.11.7`. The owner can pull these manually. Optional explicit Arvan mirror paths, without changing Docker Desktop globally:

```powershell
docker pull docker.arvancloud.ir/node:24.22.1-bookworm-slim
docker pull docker.arvancloud.ir/caddy:2.11.7
$env:NODE_IMAGE='docker.arvancloud.ir/node:24.22.1-bookworm-slim'
$env:CADDY_IMAGE='docker.arvancloud.ir/caddy:2.11.7'
docker compose -f compose.yaml -f compose.dev.yaml up --build --watch
```

The path convention follows [Arvan's Docker documentation](https://www.arvancloud.ir/fa/dev/docker). The owner successfully downloaded all seven planned base/tool images through this mirror on 2026-10-27 after transient failures. Package installation inside the build still needs npm registry access on a clean cache even after base images are available. Keep TLS verification enabled. Clearing these overrides restores the pinned Compose defaults; the download helper creates the canonical local aliases automatically.

For a host production preview, run `pnpm build` then `pnpm start --port 8080` inside `apps/web`. The launcher copies public/static assets into Next's standalone output and defaults to loopback. Stop that preview before rebuilding on Windows, and before binding Docker's gateway to the same port.

## Checks

```powershell
cd apps/web
pnpm lint
pnpm typecheck
pnpm build
pnpm exec playwright install chromium
pnpm test:e2e
```

Browser tests expect the app at `http://127.0.0.1:8080`; override `TEST_BASE_URL` when needed. `CHROMIUM_EXECUTABLE` can use an already installed browser. Tests cover both locales/themes at 360, 768 and 1440 pixels, filters, empty results, market/language isolation, dialog focus and reduced motion. Screenshots and reports are ignored runtime outputs; curated evidence belongs in `docs/evidence/`.

With development Compose Watch running, `node scripts/verify-watch.mjs` from `apps/web` verifies a reversible footer edit reaches the existing browser document, then restores the source and verifies the restoration. Run it without concurrent footer editing. Loopback `127.0.0.1` is explicitly permitted in Next's development-only origin list so the HMR connection works through Caddy. No wildcard origin allowance is used.

## Continue implementation

Read `AGENTS.md`, `docs/NIVARO_ROADMAP_EN.md`, `docs/progress.md`, and the image-first register. Do not read the stale Persian roadmap as implementation input. Follow phase dependencies and distinguish local checks, container checks and CI. Do not activate real payments/SMS or public deployment without the required separate inputs and authority.
