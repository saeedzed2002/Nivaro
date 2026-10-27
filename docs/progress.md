# Implementation progress

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
- Local/CI results will be appended after execution. No live providers or public deployment.
