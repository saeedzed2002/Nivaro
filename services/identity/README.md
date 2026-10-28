# Identity — P03 foundation, not a running service

P03 has started. This package currently contains phone normalization, strict asymmetric token primitives, public-key overlap handling and atomic Redis OTP policies. It has **no public API, database migration, persisted session, administrator password flow or frontend integration yet**. It is not connected to the gateway and must not be presented as working authentication. P02 continues serving the store unchanged.

## Dependency gate

Direct dependencies are pinned in `pyproject.toml`. The first Linux resolution attempt failed fetching `argon2-cffi` metadata from PyPI, and a single host connectivity probe also timed out. There is **no identity lockfile or frozen Linux installation yet**. Do not copy catalog's lockfile or downgrade dependencies to conceal that gap.

When package access is restored, run from the repository root:

```powershell
./scripts/Prepare-IdentityDependencies.ps1
./scripts/Verify-IdentityFoundation.ps1
```

The download helper uses the already downloaded `python:3.13.18-slim-bookworm` image, reuses `nivaro-python-download-cache`, and installs the cached uv wheel when present. It creates the initial lock only if missing, then syncs frozen. Requests have a 20-second timeout with no retries; the helper does not pull base images. New direct dependencies beyond catalog are Redis client 8.1.0, PyJWT 2.15.1, cryptography 50.0.2, pwdlib 0.3.1, argon2-cffi 25.1.0 and email-validator 2.3.0, plus resolver-selected transitive packages. A successful helper run is installation evidence, not service acceptance. The verification helper refuses to run without that environment, uses its own internal network/disposable Redis with no host port, and cleans up only resources created by that invocation. It has not yet completed the Linux gate.

## Current evidence

- Selected Linux Ruff 0.17.2 passes lint and format checks using catalog's existing checker environment.
- Preliminary Windows Python 3.12.3 checks: 26 tests pass against an actual disposable Redis 8.10.3 container. Existing host tools were not changed: PyJWT 2.10.1, cryptography 50.0.0, redis client 5.0.8, pydantic-settings 2.5.2, pytest 9.1.1. These differ from the selected runtime and do **not** establish Linux dependency compatibility, strict type checks or release acceptance.
- Follow-up token-header hardening rejects non-string `kid` values as controlled token errors; the security-only suite then passed all 17 tests. Full foundation coverage now has 27 tests; the final full Linux run is still pending.
- Redis tests require `IDENTITY_TEST_REDIS_URL` pointing to a disposable instance. They use random per-test HMAC namespaces, no `FLUSHDB`, and do not inspect production secrets. The temporary local test container is removed after the check; no persistent store data is involved.

## Security boundaries

- Codes have six cryptographically generated digits, 120-second TTL, five attempts and 60-second resend cooldown. Anchored fixed windows enforce five accepted sends/hour, thirty/day and configurable source-IP request limits. Rate limits and replacement are atomic Lua operations; parallel verification consumes at most once. Replacing a challenge invalidates the previous ID. Invalid challenge IDs cannot consume a newer challenge's attempts.
- Redis holds HMAC-bound code values and HMAC-derived phone/IP keys, not raw codes or identifiers. Raw codes exist only transiently for delivery; challenge repr hides them. The caller must normalize phones first, enforce the development test-number allowlist, and obtain source IP only through a trusted gateway. Redis errors must become controlled unavailable responses; never bypass limits.
- Scripts target standalone Redis with `noeviction`, bounded memory, authentication and internal-only network access. They do not support Redis Cluster. Integration coverage of OOM behavior and production Redis configuration remains pending.
- Access tokens enforce RS256, known `kid`, issuer, strict audience, required claims, expiration and session kind. Customer tokens cannot carry administrator permissions. Public-only overlap keys allow rotation; remove a retired key after the token overlap period. Token verification alone does **not** verify database revocation/account status. No protected route may rely on it alone.
- Release configuration rejects mock login and non-HTTPS origins. This is a startup-settings guard, not a complete deployment or CSRF implementation.

## Next implementation

1. Resolve/freeze dependencies; run the selected Linux tests and strict types. Add identity's database/limited role and migrations, then prove catalog cannot access identity data and vice versa.
2. Implement database-backed session families and consumed refresh hashes, locking rotation, bounded duplicate-refresh handling, per-device/all-device revocation, disabled accounts, administrator password changes and minimal redacted audit records. Store refresh/CSRF hashes only. Coordinate browser refresh across tabs; a bounded equivalent concurrent request can return a retryable conflict without issuing another token or revoking the family. Test late reuse separately.
3. Add mock-only allowlisted OTP routes, administrator Argon2id credentials/bootstrap, permissions, secure separate cookies, same-origin checks and session-bound synchronizer CSRF. Fail closed on unavailable authoritative state. No default administrator password or real SMS adapter.
4. Export canonical contracts, integrate the already pictured five page templates, and verify both languages/themes, mobile/desktop and complete browser login/refresh/logout/ownership journeys. Do not invent a dashboard or pending commerce features.

Sources consulted for the implementation primitives: [PyJWT usage](https://pyjwt.readthedocs.io/en/stable/usage.html), [atomic Redis Lua semantics](https://redis.io/docs/latest/develop/programmability/eval-intro/), and [FastAPI token/password guidance](https://fastapi.tiangolo.com/tutorial/security/oauth2-jwt/). The canonical roadmap controls Nivaro's stricter session/cookie contracts.
