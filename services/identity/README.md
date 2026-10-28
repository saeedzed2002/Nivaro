# Identity — P03 foundation, not a running service

P03 has started. This package currently contains phone normalization, strict asymmetric token primitives, public-key overlap handling and atomic Redis OTP policies. It has **no public API, database migration, persisted session, administrator password flow or frontend integration yet**. It is not connected to the gateway and must not be presented as working authentication. P02 continues serving the store unchanged.

## Selected Linux dependency baseline

Direct dependencies are pinned in `pyproject.toml`, and `uv.lock` now records the selected transitive versions, artifact URLs and hashes. Direct PyPI downloads failed on the owner's connection. On 2026-10-28, the provider-documented [Runflare HTTPS mirror](https://runflare.com/mirrors/pypi-mirror/) resolved and installed the selected Linux dependencies successfully without a VPN or changing global proxy/DNS/TLS settings. This lock records Runflare URLs; a future switch to another source requires a deliberate lock refresh and verification, not a hand-edited URL replacement.

To prepare or verify the environment from the repository root:

```powershell
./scripts/Prepare-IdentityDependencies.ps1 -IndexUrl 'https://mirror-pypi.runflare.com/simple'
./scripts/Verify-IdentityFoundation.ps1
```

The download helper uses the already downloaded `python:3.13.18-slim-bookworm` image, reuses `nivaro-python-download-cache`, and installs the cached uv wheel when present. It creates the initial lock only if missing, then syncs frozen. Requests have a 20-second timeout with no retries; the helper does not pull base images. `-IndexUrl` sets `UV_DEFAULT_INDEX` and `PIP_INDEX_URL` only inside this disposable container; its default remains official PyPI. An existing lock keeps its recorded artifact sources even when this argument changes. Embedded credentials and non-HTTPS URLs are rejected. No extra index or trusted-host/TLS bypass is used.

New direct dependencies beyond catalog are Redis client 8.1.0, PyJWT 2.15.1, cryptography 50.0.2, pwdlib 0.3.1, argon2-cffi 25.1.0 and email-validator 2.3.0. A successful helper run is installation evidence, not service acceptance. The verification helper refuses to run without that environment, uses its own internal network/disposable Redis with no host port, and cleans up only resources created by that invocation.

## Current evidence

- Selected Python 3.13.18 Linux environment: Ruff 0.17.2 lint/format pass; strict mypy 2.4.0 passes all 7 source files; **27 tests pass in 15.83s** against disposable Redis 8.10.3. An irrelevant warning from the intentional forged-token test's short HMAC key was removed by lengthening that test key; the focused test then passed without warnings. No production algorithm or key policy changed.
- A new temporary environment also installed all 52 locked packages using `uv sync --frozen --offline` with Docker networking disabled. This verifies reuse of the populated named cache, not cold offline installation on another machine.
- Preliminary Windows Python 3.12.3 checks: 26 tests pass against an actual disposable Redis 8.10.3 container. Existing host tools were not changed: PyJWT 2.10.1, cryptography 50.0.0, redis client 5.0.8, pydantic-settings 2.5.2, pytest 9.1.1. These differ from the selected runtime and do **not** establish Linux dependency compatibility, strict type checks or release acceptance.
- The earlier provisional Windows results above are historical and are superseded by the selected Linux foundation checks. Running API/session/browser and full P03 acceptance are still pending.
- Redis tests require `IDENTITY_TEST_REDIS_URL` pointing to a disposable instance. They use random per-test HMAC namespaces, no `FLUSHDB`, and do not inspect production secrets. The temporary local test container is removed after the check; no persistent store data is involved.

## Security boundaries

- Codes have six cryptographically generated digits, 120-second TTL, five attempts and 60-second resend cooldown. Anchored fixed windows enforce five accepted sends/hour, thirty/day and configurable source-IP request limits. Rate limits and replacement are atomic Lua operations; parallel verification consumes at most once. Replacing a challenge invalidates the previous ID. Invalid challenge IDs cannot consume a newer challenge's attempts.
- Redis holds HMAC-bound code values and HMAC-derived phone/IP keys, not raw codes or identifiers. Raw codes exist only transiently for delivery; challenge repr hides them. The caller must normalize phones first, enforce the development test-number allowlist, and obtain source IP only through a trusted gateway. Redis errors must become controlled unavailable responses; never bypass limits.
- Scripts target standalone Redis with `noeviction`, bounded memory, authentication and internal-only network access. They do not support Redis Cluster. Integration coverage of OOM behavior and production Redis configuration remains pending.
- Access tokens enforce RS256, known `kid`, issuer, strict audience, required claims, expiration and session kind. Customer tokens cannot carry administrator permissions. Public-only overlap keys allow rotation; remove a retired key after the token overlap period. Token verification alone does **not** verify database revocation/account status. No protected route may rely on it alone.
- Release configuration rejects mock login and non-HTTPS origins. This is a startup-settings guard, not a complete deployment or CSRF implementation.

## Next implementation

1. Preserve the verified lock and repeat selected Linux checks after changes. Add identity's database/limited role and migrations, then prove catalog cannot access identity data and vice versa.
2. Implement database-backed session families and consumed refresh hashes, locking rotation, bounded duplicate-refresh handling, per-device/all-device revocation, disabled accounts, administrator password changes and minimal redacted audit records. Store refresh/CSRF hashes only. Coordinate browser refresh across tabs; a bounded equivalent concurrent request can return a retryable conflict without issuing another token or revoking the family. Test late reuse separately.
3. Add mock-only allowlisted OTP routes, administrator Argon2id credentials/bootstrap, permissions, secure separate cookies, same-origin checks and session-bound synchronizer CSRF. Fail closed on unavailable authoritative state. No default administrator password or real SMS adapter.
4. Export canonical contracts, integrate the already pictured five page templates, and verify both languages/themes, mobile/desktop and complete browser login/refresh/logout/ownership journeys. Do not invent a dashboard or pending commerce features.

Sources consulted for the implementation primitives: [PyJWT usage](https://pyjwt.readthedocs.io/en/stable/usage.html), [atomic Redis Lua semantics](https://redis.io/docs/latest/develop/programmability/eval-intro/), and [FastAPI token/password guidance](https://fastapi.tiangolo.com/tutorial/security/oauth2-jwt/). The canonical roadmap controls Nivaro's stricter session/cookie contracts.
