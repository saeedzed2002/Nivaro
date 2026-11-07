# Catalog — storefront and administration

Catalog owns product facts, physical variants, independent market offers and compatibility evaluations. It has no cart/order database access and no reservation or payment endpoint. The gateway connects this service to the home, collection, details, comparison and temporary builder pages. See [progress](../../docs/progress.md) for exact verified revisions and acceptance evidence.

## P04 protected administration

`GET /api/v1/admin/catalog/products` supports bounded pagination, publication status, category UUID and normalized name/exact case-insensitive SKU search. `GET /api/v1/admin/catalog/products/{product_id}` returns the selected product, including drafts/archives, only to an authorized catalog manager. Staff responses include the product edit revision and each variant's stock revision. Public read rules remain unchanged.

Catalog accepts only `nivaro_admin_access`, verifies RS256 with public JWKS, strict issuer/audience/kind/session identifiers and `catalog.write`, then calls identity for fresh authoritative authorization on every request. Customer tokens never grant staff access. Public keys cache for 60 seconds with a bounded unknown-key refresh; permissions/session status do not cache. Calls use a shared bounded HTTP client, a four-second total budget, bounded response bodies and no redirects/environment proxy. An unavailable or invalid authority response denies access; public catalog reads do not depend on identity availability.

`CATALOG_IDENTITY_URL` defaults to `http://identity:8000`. Compose mounts the dedicated caller secret through `CATALOG_IDENTITY_SERVICE_KEY_FILE`; no identity database credential or private browser-signing key is shared. Every mutation uses the same dependency, which checks allowed origins and forwards session CSRF for authoritative validation. See [identity boundary](../identity/README.md#catalog-authorization-boundary--p04).

All routes below are relative to `/api/v1/admin/catalog/products`:

| Method/path | Contract |
| --- | --- |
| `POST /` | Create a draft with bilingual descriptions; server assigns UUID/revision and an unready empty image. Unique slug makes repeated creation conflict rather than duplicate. |
| `PUT /{product_id}` | Replace the explicitly writable content fields, with `expected_version`. No status, readiness, image path or counters accepted. |
| `PUT /{product_id}/status` | Set draft/published/archived using `expected_version`. Publication requires complete content, a ready image and valid variants. No deletion route. |
| `POST /{product_id}/variants` | Add a unique uppercase SKU and typed specifications, with product `expected_version`; initial stock is zero/unverified, no offers. |
| `PUT /{product_id}/variants/{variant_id}` | Replace variant metadata/specifications with product `expected_version`; technical and stock revisions advance. Hardware kind cannot change in place. |
| `PUT /{product_id}/variants/{variant_id}/stock` | Set absolute `on_hand` and `stock_verified`, requiring product `expected_version`, `expected_stock_version` and reason. Cannot edit reserved units or reduce on-hand below reservations. |
| `PUT /{product_id}/variants/{variant_id}/offers` | Set one explicit market/currency offer, with product `expected_version`, `expected_price_version` (zero for create), source and reason. IRR amounts are whole tomans in rials; USD is independent cents. Reference observations cannot be sold. Sale eligibility requires published/ready product and verified stock. |
| `GET /{product_id}/audit` | Bounded history of actor, before/after values, reason, request ID and timestamp; same staff authorization as mutations. |

The application opens one transaction after authorization, locks product before variant/offer, checks the expected revisions, and commits the mutation and audit together. A competing or repeated stale write returns `409`; reload before retrying, never silently rebase an absolute stock count. Unchanged commands do not advance revisions or add audit entries. `catalog_audit_entries` rejects UPDATE/DELETE through a trigger. Prices and stock changes cannot commit without their audit entry. Technical and price revision triggers remain active. Future reservation writers must lock variants in identifier order and advance their stock revision, without taking a product lock after a variant lock. See [PostgreSQL row locks](https://www.postgresql.org/docs/current/explicit-locking.html#LOCKING-ROWS) and [SQLAlchemy transaction boundaries](https://docs.sqlalchemy.org/en/20/orm/session_transaction.html#managing-transactions).

No new dependency was needed for mutations. The staff UI at `/{locale}/admin/products` connects listing, basic creation/editing, publication transitions, stock adjustment and audit history. The editor also supports all typed variant specifications/evidence and independent market-price forms with exact whole-toman/dollar input, explicit confirmation and stale-version recovery. Private media jobs/upload readiness and cache integration remain P04 work. A newly created draft cannot be published until the trusted image pipeline exists and produces its ready image; there is deliberately no manual readiness override. These APIs do not activate checkout, real provider delivery or live international fulfillment.

Category administration at `/{locale}/admin/categories` uses `GET/POST /api/v1/admin/catalog/categories`, `PUT /{id}` and `GET /{id}/audit`. Names are bilingual, slugs unique, and edits require `expected_version`. The list includes direct product/child counts and is bounded to 1000 categories. The same fresh staff authorization and CSRF boundary applies. Structural writes acquire transaction advisory lock `(71404, 1)` before category row locks; all future category writers must follow this order. Concurrent moves cannot create a cycle or third level. Category IDs and product references remain stable; no deletion or arbitrary image-path write is exposed. Revision and append-only audit commit atomically. The UI preserves failed/stale drafts and requires explicit replacement after comparing the current server record.

The catalog lock was regenerated from the existing regional cache for PyJWT/cryptography/HTTPX runtime dependencies; all prior package versions were verified unchanged. The normal Dockerfile exports frozen versions/hashes and installs from explicit `PYTHON_INDEX_URL` (official PyPI by default), matching identity's portable build approach. The offline Dockerfile keeps using the lock's mirror cache. No new base image or download was required locally.

## Verification boundary

The selected baseline is Python 3.13.18, uv 0.13.5 and the committed `uv.lock`, tested against PostgreSQL 18.6. Linux checks cover Ruff, formatting, strict mypy, backend tests, Alembic and canonical OpenAPI drift; exact run counts and revisions are in the progress log. The release image runs as a non-root user; the one-shot init service applies migrations and the repeatable seed before API readiness. Earlier provisional Windows checks are historical evidence in the progress log, not the release baseline.

The local acceptance helpers verify migrations from zero in a separate disposable database, database changes reaching the browser without a web rebuild, and actual API outage/recovery. `CATALOG_DISPOSABLE_TESTS=1` enables a committed two-session stock-race probe only in the fresh local test database and isolated CI database. Other API tests use an outer rollback transaction with per-request savepoints. Never set that flag against owner/live commerce data. These checks do not establish real inventory, approved store prices, checkout reservations or live market readiness.

## Database foundation

From the repository root:

```powershell
./scripts/Initialize-LocalSecrets.ps1
docker compose up -d --build --wait
```

Secrets are generated once into ignored `work/secrets/`; existing values are preserved. Do not commit them. The application role `nivaro_catalog` owns only its catalog database and has no superuser, role-creation, replication or database-creation privilege. Base Compose includes the catalog and publishes no database port; `compose.catalog.yaml` is retained only as a compatibility no-op. PostgreSQL 18 uses a persistent volume mounted at `/var/lib/postgresql`; never delete that volume to rerun a migration or seed.

The init script runs automatically only for a fresh volume. For an already initialized volume requiring this first database, explicitly run `sh /docker-entrypoint-initdb.d/10-catalog.sh` inside the PostgreSQL container; the script preserves existing databases and roles. It deliberately does not rotate an existing role password when a secret file is changed. Do not regenerate secrets independently of a deliberate credential rotation.

## Maintenance and verification

1. Preserve `uv.lock`; use `uv sync --frozen` for subsequent installs. A mounted development environment is not evidence of a clean application-image build.
2. Keep migrations in the one-shot `catalog-init` service. API workers must not race to apply migrations at startup.
3. Set `CATALOG_DB_HOST`, `CATALOG_DB_PORT`, `CATALOG_DB_NAME`, `CATALOG_DB_USER` and `CATALOG_DB_PASSWORD_FILE` for the intended catalog instance. Defaults target the Compose network and `/run/secrets/catalog_db_password`. Never print password values or database URLs containing them.
4. Run `uv run alembic upgrade head`, then `uv run python -m nivaro_catalog.infrastructure.seed`. The seed is insert-only and repeatable; it never overwrites an existing offer, stock counter or technical fact. Updating existing facts needs a newer `spec_version`, not another seed run.
5. Run `uv run pytest`, `uv run ruff check .`, `uv run ruff format --check .`, `uv run mypy src`, and `uv run alembic check`. Database/API tests skip unless `CATALOG_DB_HOST` is explicitly set; a unit-only pass is not integration evidence. Test against a dedicated instance or the known local demo database, not live commerce data. Tests roll back their fixture mutations.
6. Export `uv run python -m nivaro_catalog.export_openapi ../../contracts/openapi/catalog.json`, generate frontend types with the selected `openapi-typescript`, and verify regeneration produces no diff. Offline diagnostic exports under `work/` are not release contracts.
7. Run frontend browser checks against the gateway in both languages/themes. `scripts/Verify-CatalogFresh.ps1` exercises a separate tmpfs database using the existing local release image and mounted Linux test environment. It never resets the persistent catalog volume. From `apps/web`, run `NIVARO_DEMO_RUNTIME_CHECK=1 node scripts/verify-catalog-runtime.mjs` using your shell's environment-variable syntax for the guarded local-demo database/UI and outage/recovery check. Do not run it against live commerce data.

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
