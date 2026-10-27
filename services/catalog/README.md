# Catalog — P02 foundation, not release-verified

Catalog owns product facts, physical variants, independent market offers and compatibility evaluations. It has no cart/order database access and no reservation or payment endpoint. The running storefront still uses its P01 research fixtures; this service has not been wired to the gateway or web pages yet.

## Verification boundary

The selected runtime remains Linux/Python 3.13.18 with the direct dependency pins in `pyproject.toml`. The bounded package bootstrap failed on PyPI connectivity, and the owner confirmed internet is unavailable. **No `uv.lock`, frozen backend installation, backend image, strict mypy result or canonical generated frontend contract is established.** Do not present this slice as a completed P02 or downgrade the declared dependencies to make the checks appear green. The supplemental Hatchling 1.32.4 pin is from existing cached package metadata and remains subject to the same installation/compatibility probe.

Offline checks used the already installed Windows Python 3.12.3 environment without modifying it: FastAPI 0.115.0, Pydantic 2.9.2, pydantic-settings 2.5.2, SQLAlchemy 2.0.35, Alembic 1.13.2, psycopg/psycopg-binary 3.3.4, HTTPX 0.27.2, pytest 9.1.1, pytest-asyncio 0.24.0 and Ruff 0.16.3. These are **provisional validation tools**, not selected production versions. PostgreSQL tests used the actual pinned 18.6 Linux image.

## Database foundation

From the repository root:

```powershell
./scripts/Initialize-LocalSecrets.ps1
docker compose -f compose.yaml -f compose.catalog.yaml up -d --pull never postgres
```

Secrets are generated once into ignored `work/secrets/`; existing values are preserved. Do not commit them. The application role `nivaro_catalog` owns only its catalog database and has no superuser, role-creation, replication or database-creation privilege. The overlay publishes no database port. PostgreSQL 18 uses a persistent volume mounted at `/var/lib/postgresql`; never delete that volume to rerun a migration or seed.

The init script runs automatically only for a fresh volume. For an already initialized volume requiring this first database, explicitly run `sh /docker-entrypoint-initdb.d/10-catalog.sh` inside the PostgreSQL container; the script preserves existing databases and roles. It deliberately does not rotate an existing role password when a secret file is changed. Do not regenerate secrets independently of a deliberate credential rotation.

## Complete after connectivity returns

1. Resolve the selected backend dependencies using `uv 0.13.5` and the existing Python 3.13.18 base image; produce `uv.lock`, verify a frozen install and run Ruff/mypy/tests in that environment. Test the package/build-backend combination before treating the pins as accepted.
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

Research seed: six products, seven physical variants, six independently sourced offer observations. The 9800X3D tray and boxed variants deliberately have separate Iran/USD observations; these do not represent the same packaging. The 9700X has no invented price. All stock is unverified and all research offers are unavailable for sale. Generic existing images remain labeled illustrations.

Typed specifications reject arbitrary unknown attributes. Specification/offer revisions are guarded by PostgreSQL triggers; changed technical facts/evidence require a newer specification revision, and changed price/eligibility requires a newer offer revision. Physical stock invariants, currency/toman rules, variant/market uniqueness and category depth are also database-enforced.

See [compatibility policy](../../docs/catalog/COMPATIBILITY_RULES.md) for sources, limitations and the power estimate. Synthetic complete-build fixtures demonstrate rule behavior, not a verified real retail configuration. Liquid radiator layouts deliberately remain `needs_review`. Saved drafts, two-system comparison, cart transfers, checkout quotes and atomic reservations belong to subsequent phase work.
