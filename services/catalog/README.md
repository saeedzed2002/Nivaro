# Catalog — P02 foundation, not release-verified

Catalog owns product facts, physical variants, independent market offers and compatibility evaluations. It has no cart/order database access and no reservation or payment endpoint. The P02 checkpoint routes this service through the gateway and connects the home, collection, details, comparison and temporary builder pages. Full phase acceptance is still pending.

## Verification boundary

The owner-assisted retry on 2026-10-27 successfully installed uv 0.13.5, resolved the selected dependencies, created `uv.lock` and completed `uv sync --frozen`, including the catalog package build. Subsequent execution inside the existing Linux/Python 3.13.18 image passed Ruff, strict mypy, all 66 tests against PostgreSQL 18.6, and `alembic check`. SQLAlchemy 2.1's updated Select typing and two variable/translation typing issues were corrected without changing the selected versions. **The checkpoint now includes a non-root image, offline frozen backend build, canonical contracts and frontend integration. Full P02 acceptance and private CI remain pending; the latest evidence is in docs/progress.md.** The dependency gate has advanced; the whole phase is not complete. The following Windows results are historical provisional evidence, superseded by these Linux checks.

Offline checks used the already installed Windows Python 3.12.3 environment without modifying it: FastAPI 0.115.0, Pydantic 2.9.2, pydantic-settings 2.5.2, SQLAlchemy 2.0.35, Alembic 1.13.2, psycopg/psycopg-binary 3.3.4, HTTPX 0.27.2, pytest 9.1.1, pytest-asyncio 0.24.0 and Ruff 0.16.3. These are **provisional validation tools**, not selected production versions. PostgreSQL tests used the actual pinned 18.6 Linux image.

## Database foundation

From the repository root:

```powershell
./scripts/Initialize-LocalSecrets.ps1
docker compose -f compose.yaml -f compose.catalog.yaml up -d --pull never postgres
```

Secrets are generated once into ignored `work/secrets/`; existing values are preserved. Do not commit them. The application role `nivaro_catalog` owns only its catalog database and has no superuser, role-creation, replication or database-creation privilege. The overlay publishes no database port. PostgreSQL 18 uses a persistent volume mounted at `/var/lib/postgresql`; never delete that volume to rerun a migration or seed.

The init script runs automatically only for a fresh volume. For an already initialized volume requiring this first database, explicitly run `sh /docker-entrypoint-initdb.d/10-catalog.sh` inside the PostgreSQL container; the script preserves existing databases and roles. It deliberately does not rotate an existing role password when a secret file is changed. Do not regenerate secrets independently of a deliberate credential rotation.

## Baseline procedure and remaining acceptance (see latest progress)

1. The selected dependency resolution/install and Linux checks now pass. Preserve `uv.lock`; use `uv sync --frozen` for subsequent installs and verify a fresh/offline application-image build rather than claiming that the mounted development environment proves it.
2. Add and verify the non-root catalog image and a one-shot migration/seed job. API workers must not race to apply migrations at startup.
3. Set `CATALOG_DB_HOST`, `CATALOG_DB_PORT`, `CATALOG_DB_NAME`, `CATALOG_DB_USER` and `CATALOG_DB_PASSWORD_FILE` for the intended catalog instance. Defaults target the Compose network and `/run/secrets/catalog_db_password`. Never print password values or database URLs containing them.
4. Run `uv run alembic upgrade head`, then `uv run python -m nivaro_catalog.infrastructure.seed`. The seed is insert-only and repeatable; it never overwrites an existing offer, stock counter or technical fact. Updating existing facts needs a newer `spec_version`, not another seed run.
5. Run `uv run pytest`, `uv run ruff check .`, `uv run ruff format --check .`, `uv run mypy src`, and `uv run alembic check`. Database/API tests skip unless `CATALOG_DB_HOST` is explicitly set; a unit-only pass is not integration evidence. Test against a dedicated instance or the known local demo database, not live commerce data. Tests roll back their fixture mutations.
6. Export `uv run python -m nivaro_catalog.export_openapi ../../contracts/openapi/catalog.json`, generate frontend types with the selected `openapi-typescript`, and verify regeneration produces no diff. Offline diagnostic exports under `work/` are not release contracts.
7. Connect the existing pages and implement the already pictured comparison/builder templates, including both themes/locales and unavailable/error states. Add real source-backed component records before demonstrating a complete real system. Complete Docker/browser/CI gates and record evidence before marking P02 verified.

## Implemented public contracts

- `GET /health/live`, `GET /health/ready` (readiness checks the migration revision).
- `GET /api/v1/catalog/categories`.
- `GET /api/v1/catalog/products`: bounded pagination, normalized literal Persian/Latin token-prefix search, category/brand, independent-market price and available-stock filters; deterministic featured/name/newest/price sorting. Rating sort is intentionally rejected until approved reviews exist in P08.
- `GET /api/v1/catalog/products/{slug}` and `GET /api/v1/catalog/variants/{variant_id}`; unpublished or image-unready products are hidden.
- `POST /api/v1/catalog/comparisons`: exactly two distinct variants, same category, one market/currency; normalized scalar facts, unknowns and differences, no winner or invented benchmarks.
- `POST /api/v1/catalog/build-evaluations`: bounded selections, revision-bound findings, partial research subtotals, missing prices and aggregate availability; no persistence, price guarantee or reservation.

Request bodies are capped at 64 KiB including chunked requests. Errors carry a bounded request ID and never echo database errors or raw invalid input. Stored facts are revalidated at the read boundary; invalid data returns an unavailable result instead of guessed facts. OpenAPI/docs are exported locally and not exposed by the app.

## Data and policy limits

Research seed: twelve products, thirteen physical variants, six independently sourced offer observations. Six additional core parts have manufacturer evidence and no invented market offers. The 9800X3D tray and boxed variants deliberately have separate Iran/USD observations; these do not represent the same packaging. The 9700X has no invented price. All stock is unverified and all research offers are unavailable for sale. Generic existing images remain labeled illustrations.

Typed specifications reject arbitrary unknown attributes. Specification/offer revisions are guarded by PostgreSQL triggers; changed technical facts/evidence require a newer specification revision, and changed price/eligibility requires a newer offer revision. Physical stock invariants, currency/toman rules, variant/market uniqueness and category depth are also database-enforced.

See [compatibility policy](../../docs/catalog/COMPATIBILITY_RULES.md) for sources, limitations and the power estimate. Synthetic complete-build fixtures demonstrate rule behavior, not a verified real retail configuration. Liquid radiator layouts deliberately remain `needs_review`. Saved drafts, two-system comparison, cart transfers, checkout quotes and atomic reservations belong to subsequent phase work.

## Bounded-download local recovery

The normal Dockerfile is the clean-machine/CI build. On the owner machine, the existing download cache can supply a new frozen backend environment without network:

```powershell
./scripts/Prepare-CatalogCache.ps1
docker build --pull=false --network=none --build-context dependency-cache=./work/python-cache -f services/catalog/Dockerfile.offline -t nivaro-catalog:release services/catalog
docker build --pull=false -f apps/web/Dockerfile.cached -t nivaro-web:release apps/web
docker compose up -d --no-build --pull never --wait
```

Run from the repository root. The frontend recovery requires the already populated `nivaro-web:development` Linux image; missing dependencies get a bounded fetch. This is not an offline bootstrap on an empty machine. Never remove the database volume or regenerate existing secrets.

Canonical contract check: run `python -m nivaro_catalog.export_openapi /contracts/openapi/catalog.json --check` in the frozen catalog environment with contracts mounted, then `pnpm contracts:check` in apps/web. Regenerate using the export command without `--check` and `pnpm contracts:generate`. Type artifacts stay inside the frontend build context.
