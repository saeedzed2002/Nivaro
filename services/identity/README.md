# Identity — P03 local accounts and separate staff sessions

The identity API now runs behind the same-origin gateway. PostgreSQL owns accounts, credentials, session families, consumed refresh hashes, addresses and minimal audit events. Redis owns atomic OTP/rate-limit state. Five image-first pages are connected: customer login, account overview, profile, addresses and staff login. Full administrative workspaces, processed avatars and real SMS are later phases.

## Run and inspect

From the repository root (existing volumes and secret values are preserved):

```powershell
./scripts/Initialize-LocalSecrets.ps1
docker compose up -d --build --wait
./scripts/Verify-IdentityService.ps1
./scripts/Verify-IdentityBrowser.ps1
```

Open `/fa/login` or `/en/login` on `http://127.0.0.1:8080`. Local mock login accepts only `+12025550100` and `+12025550101`; its random code is shown explicitly as a local test code. No real SMS is sent. Account pages are `/[locale]/account`, `/account/profile` and `/account/addresses`. Staff login is `/[locale]/admin/login`; customer login never grants staff permissions.

There is **no seeded administrator**. The owner must enter their own phone, email and password interactively to create the first administrator:

```powershell
docker compose exec identity python -m nivaro_identity.manage bootstrap-admin
```

The command refuses a second bootstrap. Other operator commands are `change-admin-password`, `disable-user`, and `prune-expired`. Password entry is hidden and never passed on the command line. Password changes revoke staff sessions; disabling an account revokes both kinds. Pruning removes sessions seven days after their absolute expiry and audit events after ninety days; scheduling/backup/operational monitoring remain deployment work. Do not run pruning against another environment accidentally.

## Dependency recovery and builds

Direct dependencies are pinned in `pyproject.toml`; `uv.lock` includes resolved versions, artifact URLs and hashes. The selected baseline is Python 3.13.18 and uv 0.13.5. Direct PyPI downloads timed out on the owner's connection. The provider-documented [Runflare HTTPS mirror](https://runflare.com/mirrors/pypi-mirror/) supplied the locked Linux packages without changing global DNS/proxy/TLS settings:

```powershell
./scripts/Prepare-IdentityDependencies.ps1 -IndexUrl 'https://mirror-pypi.runflare.com/simple'
./scripts/Verify-IdentityFoundation.ps1
```

`-IndexUrl` is container-scoped, HTTPS-only, with bounded requests. Existing lockfiles retain their recorded Runflare artifact URLs; changing the helper option does not rewrite a lock. A different source requires a deliberate lock refresh and verification. No extra index, trusted-host setting or TLS bypass is used.

The normal Dockerfile has `test` and non-root `release` targets. For the existing populated Linux download cache only:

```powershell
./scripts/Prepare-CatalogCache.ps1
docker build --pull=false --network=none --build-context image-processing=./packages/python/image_processing --build-context dependency-cache=./work/python-cache -f services/identity/Dockerfile.offline -t nivaro-identity:release services/identity
docker build --pull=false --network=none --build-context image-processing=./packages/python/image_processing --build-context dependency-cache=./work/python-cache -f services/identity/Dockerfile.offline --target test -t nivaro-identity:test services/identity
./scripts/Verify-IdentityService.ps1 -TestImage nivaro-identity:test
```

These offline builds reuse downloaded artifacts; they do not establish cold offline installation on a new machine. Normal uncached build evidence belongs to the matching CI run, not an earlier phase's run.

## Security contract

- Independent database and non-superuser role; PUBLIC database access is revoked. Both catalog-to-identity and identity-to-catalog connection attempts are tested and denied. An idempotent init job adds identity to an existing PostgreSQL volume without resetting catalog.
- OTP: six random digits, 120 seconds, five verification attempts, 60-second resend interval, five sends/hour and thirty/day per normalized phone, thirty source-IP requests/hour. HMAC-bound codes and HMAC identifiers, atomic Lua replacement/consumption/limits, fail closed on Redis failure. Caddy overwrites the trusted client-IP header; identity has no host-published port. Future reverse proxies require explicit trusted-proxy configuration, not arbitrary forwarded-header trust.
- Mock delivery works only in development/test for explicit test numbers. Release settings reject mock mode and non-HTTPS origins. Compose intentionally runs development-mode identity inside the release application image for local HTTP tests.
- RS256 access JWTs with strict issuer/audience/kind/expiry/kid and public JWKS; five-minute access, thirty-day absolute customer and twelve-hour staff limits. Only identity holds the signing key. Previous public keys can overlap during rotation; no private key is shared with web/catalog.
- Each protected identity request reads authoritative database state and current permissions. No positive session cache is used; Redis loss does not grant access or erase persisted revocation. Catalog now uses the restricted fresh introspection endpoint below.
- Separate HttpOnly access/refresh cookies per session kind. Secure in release; refresh cookies restricted to the corresponding refresh path. Synchronizer CSRF and exact allowed Origin checks protect mutations. Same-origin custom-header retrieval recovers CSRF after access expiry. Tokens are never stored in JavaScript persistence or URLs.
- Opaque refresh values are stored only as hashes. User-then-session locks serialize refresh/revocation. Reuse within five seconds yields a retryable conflict without another token or revocation; later reuse revokes the family before the error response. Web Locks coordinate tabs; fallback conflict handling and auth retries are bounded. Network-loss replay of an older refresh after the grace window deliberately requires fresh login.
- Argon2id administrator credentials, generic invalid-login errors, per-email/IP limits, no public administrator signup or client role assignment. Staff access shown in the login screen derives from validated permissions; future operational admin pages remain absent.
- Address ownership and optimistic versions; concurrent address changes return conflicts. Profile accepts only the display name. Postal validation is country-aware for Iran; other countries currently receive bounded text validation, not postal deliverability verification. Saving an address is not a fulfillment promise.
- Minimal audit entries contain user ID, event and time, never codes, tokens, passwords or address bodies. Access logs are disabled. Database/Redis errors are sanitized; request bodies are bounded to 16 KiB.
- Pepper rotation invalidates outstanding OTP/CSRF state and requires reauthentication. Preserve local secrets and the Redis persistence volume; document deliberate production rotation/backup separately.

## Verification

`Verify-IdentityService.ps1` creates its own internal network, tmpfs PostgreSQL and authenticated Redis. Integration tests refuse destructive reset unless the database host has the helper's dedicated test prefix. It checks migrations from zero, repeated upgrade, drift, lint/format, strict types, API concurrency/security and canonical OpenAPI. `-TestImage` verifies the packaged image instead of a mounted environment.

## Catalog authorization boundary — P04

`POST /internal/v1/catalog/admin-check` is excluded from the public OpenAPI and blocked by the gateway's private-route rule. It requires a caller token signed with the dedicated `catalog_identity_service_key`, separate from browser signing keys and OTP secrets. The token uses fixed HS256, caller/subject `nivaro-catalog`/`catalog`, audience `nivaro-identity-introspection`, service kind and the specific introspection scope, a UUID identifier, at most 30 seconds of validity and a canonical request-body hash. Browser JWTs cannot authenticate this route. It has no business mutation; replay within its short validity can only repeat the same authorization query, which rereads database state.

The checked administrator access JWT must have a current, non-disabled identity session and `catalog.write` permission. Mutation checks additionally validate the forwarded allowed origin and session-bound CSRF token. Returns only user/session IDs, kind and current permissions, never phone, password, cookies or CSRF values. No positive permission cache is introduced; requests already authorized and in flight are not distributed transactions with later revocations.

Configure `IDENTITY_CATALOG_SERVICE_KEY_FILE` only for this consumer; Compose mounts the dedicated secret into identity and catalog. `Initialize-LocalSecrets.ps1` creates it only if absent. Existing values are never rotated implicitly. Missing configuration fails closed. The service test helper mounts catalog's source read-only solely for cross-service conformance tests; identity's application does not import catalog or access its database.

`Verify-IdentityBrowser.ps1` creates a unique `nivaro-p03-qa-*` Compose project with tmpfs data and loopback port 8082. It bootstraps a random test-only administrator via stdin, performs real browser login/profile/address/refresh/logout journeys, and destroys only that temporary stack. The main stack's accounts and OTP counters remain unchanged. Browser tests skip without this explicit disposable-project marker.

Current local evidence: 41 backend tests; strict typing for 17 source files; 15 identity browser tests including 60 template/locale/theme/width captures. The browser suite includes actual two-tab recovery, separate staff/customer sessions and role changes, and an injected API-unavailable response preserving the profile draft. Browser plugin was unavailable; existing Playwright with installed Edge was used. It is not an actual network outage test. See `docs/progress.md` for final commit/CI and outstanding phase gates.

### Builder index reachability

The normal Dockerfile exports requirements directly from `uv.lock` with `uv export --frozen`, retains hashes and exact versions, and uses `uv pip sync/install --require-hashes` against `PYTHON_INDEX_URL` (default official PyPI). This avoids forcing an external CI runner through a regional mirror. The application wheel is then installed with `--no-deps`; its build backend remains pinned in `pyproject.toml`. The offline Dockerfile and local dependency helper still use the original frozen lock/cache. No source URL is silently replaced in the lock, no version is upgraded, and no hash/TLS check is disabled. The first P03 CI run demonstrated Runflare connection timeouts from GitHub while official PyPI worked; the follow-up run verifies this portable install path.

## Private profile images

Customer and staff avatar slots are separate for the same user. `/api/v1/me/avatar` and `/api/v1/admin/me/avatar` enforce current session and CSRF on mutations. Uploads are bounded to 8 MiB and 30 seconds, with authentication checked again after upload I/O. Replacements preserve the active image until 128/256-pixel WebP outputs activate. Version conflicts return 409. Removal fences pending activation. Image delivery requires the owning session and uses private, no-store responses.

Include `compose.media.yaml` for persistent avatar storage, the dedicated identity worker and recoverable dispatcher. Its broker user and storage are separate from catalog. Original/stale attempt retention is seven days, with active and pending data preserved. The staff profile supports all staff roles, with email and role read-only.

## Cart customer authorization boundary — P05

`POST /internal/v1/cart/customer-check` is private and excluded from public OpenAPI. It uses the separate `cart_identity_service_key`, configured through `IDENTITY_CART_SERVICE_KEY_FILE`. The caller must be `nivaro-cart`/`cart`, with scope `cart.customer_introspect`, service kind, the fixed introspection audience and a request-body-bound HS256 token valid for at most 30 seconds. Catalog credentials and browser/admin tokens cannot authorize it. Missing key configuration fails closed; the existing catalog route retains its own key/scope.

`POST /internal/v1/service-tokens` uses HTTP Basic with client ID `orders` and the dedicated secret at `IDENTITY_ORDERS_CLIENT_SECRET_FILE`. Supply JSON fields `audience` and `scope`. The authorized audience is `nivaro-catalog` and supported scopes are `catalog.quote`, `catalog.reserve` and `catalog.finalize`. Each request issues a 30-second RS256 bearer token for one scope. Catalog verifies signatures using Identity's existing JWKS and checks the service subject, kind, audience, scope and expiry. Run the local secrets initializer to create the dedicated file while retaining existing credentials.

The supplied browser token must resolve to a current, non-disabled customer session. Mutating checks also validate the original allowed origin and that same session's CSRF token. Only user/session IDs, customer kind and empty customer permissions are returned. Identity owns all session checks and imports no cart database models in application code. No positive session-status cache is introduced.

The service verification helper additionally mounts cart source read-only for integration tests and creates a separate disposable cart database/role. It tests the actual cart client, real same-origin login/logout, revoked-cookie rejection even when a guest cookie is present, and a second customer's separate cart. The running local identity image is not replaced merely by adding this capability; candidate/runtime status is recorded in `docs/progress.md`.
