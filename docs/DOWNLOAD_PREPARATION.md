# Download preparation for the planned local stack

## P04 preflight — 2026-10-28 (current)

The local image inventory was checked before starting P04. All seven base images listed below are already present, including `rabbitmq:4.4.0-management`; no additional base-image pull is currently required. APIs and Linux workers reuse the Python base. A separate `redis-cache` process will reuse the existing Redis image. No new host Python, database, generic FastAPI/Celery image, npm package, broker image or native compiler is requested for this phase's initial implementation.

New direct Python packages: `celery==5.6.3`, `Pillow==13.0.0`, `python-multipart==0.0.32`, plus their resolved dependencies. Catalog will also need the already selected/cached token, cryptography, HTTP and Redis libraries; these are included in the combined preparation check. Exact release metadata was checked against [Celery](https://pypi.org/pypi/celery/5.6.3/json), [Pillow](https://pypi.org/pypi/Pillow/13.0.0/json) and [python-multipart](https://pypi.org/pypi/python-multipart/0.0.32/json). `aio-pika` is deferred to domain-event work; Celery supplies its own Kombu/AMQP dependency chain. S3/Boto3 and an SMS provider SDK are not needed for local storage/mock delivery.

Run this owner-operated preparation in PowerShell, with Docker Desktop's Linux engine running:

```powershell
cd D:\Project\Nivaro
.\scripts\Prepare-P04Dependencies.ps1 -IndexUrl https://mirror-pypi.runflare.com/simple
```

Then verify without any container networking:

```powershell
.\scripts\Prepare-P04Dependencies.ps1 -Offline -IndexUrl https://mirror-pypi.runflare.com/simple
```

For official PyPI, omit `-IndexUrl` on both commands. Keep the same index when checking its cache; cache entries and the resulting lockfile retain registry source information. Do not run commands concurrently against the same preparation directory. The helper validates HTTPS, never pulls a base image, uses a 20-second HTTP timeout with zero retries, reuses the pinned uv seed wheel where present and requires binary wheels rather than downloading a compiler. Failed downloads remain incomplete; no network or TLS settings are changed.

The helper creates an isolated Linux environment and lockfile under ignored `work/p04-dependencies/`, using `nivaro-python-download-cache`. It combines existing direct dependencies and constrains their current locked transitive versions, rejecting any existing lock disagreement. Neither service's manifest, lockfile, environment nor running container is changed. Success prints `P04_DEPENDENCIES_READY` after dependency consistency, imports and a WebP encode/decode check. It also writes `ready.json` bound to the generated lock hash; this is preparation evidence, not broker/worker/application acceptance. Final service-specific locks and integration checks still follow during implementation.

Current result: initial offline probes found missing packages. After the owner-facing commands were provided, a successful preparation marker and lock appeared on disk. The agent then independently reran the mirror-source helper with `--network none`: **72 packages resolved, 70 installed packages checked, consistency/imports/WebP roundtrip passed**. The download is now present and the P04 preparation gate is satisfied; no further owner download is currently needed. Existing P03 service environments are preserved. This does not establish service integration, a clean-machine offline install or future package requirements.

A further independent check used a brand-new `/tmp/p04-fresh` environment in a disposable container, the frozen preparation lock and existing download cache with `--network none`. All 70 packages installed successfully, consistency checks passed and the WebP roundtrip printed `FRESH_OFFLINE_P04_OK`. The existing `.venv` was not reused. Preserve the named cache; this is still not an empty-cache/clean-machine guarantee.

## Historical baseline inventory

Verified on 2026-10-27 against the canonical English roadmap and Docker Hub tag API. All seven tags below were reported active with a `linux/amd64` variant. This metadata check did not download layers, validate mirror availability, establish digests of local images or prove runtime compatibility.

Subsequent owner-assisted verification on the same date: all seven images were downloaded through Arvan and inspected locally, including their canonical aliases and repository digests. The current web release and development images built successfully. A frozen/offline install plus production build inside the cached Linux development image passed with `--network none`. This confirms the existing web dependency environment can rebuild offline; it does not establish a fresh-machine build or backend offline readiness. Details are in [progress](progress.md).

## Base images

| Image | Use |
| --- | --- |
| `node:24.22.1-bookworm-slim` | Web build/development and release runtime |
| `caddy:2.11.7` | Gateway |
| `python:3.13.18-slim-bookworm` | Shared base for APIs and Python workers |
| `postgres:18.6-bookworm` | Database engine; separate databases/roles for the six services |
| `rabbitmq:4.4.0-management` | Domain events and task queues; includes local management UI |
| `redis:8.10.3` | Both state and cache instances reuse one downloaded image |
| `axllent/mailpit:v1.32.0` | Optional later development email inbox; tools profile |

Docker Hub metadata endpoints: `https://hub.docker.com/v2/repositories/library/{name}/tags/{tag}` for the six official images and `https://hub.docker.com/v2/repositories/axllent/mailpit/tags/v1.32.0` for Mailpit. Availability is distinct from a successful build. Recheck compatibility before introducing later services.

## Owner-operated downloads

Keep Docker Desktop's Linux engine running. From PowerShell:

```powershell
Set-Location D:\Project\Nivaro
.\scripts\Fetch-Images.ps1 -IncludeTools
```

The script downloads sequentially from Arvan, skips existing correct-platform canonical tags, stops on the first failure without automatic retry, and adds local canonical aliases for successfully mirrored images. Retagging does not download a second copy. It does not start containers, change global registry/TLS settings or delete anything. Downloads run only when the owner executes the script; this documentation step did not run pulls.

To inspect the list without connecting to Docker, or choose the official registry:

```powershell
.\scripts\Fetch-Images.ps1 -IncludeTools -ListOnly
.\scripts\Fetch-Images.ps1 -IncludeTools -Source DockerHub
docker image ls
```

Arvan's documented explicit path is `docker.arvancloud.ir/<ImageName>`: [official guide](https://www.arvancloud.ir/fa/dev/docker). A timeout is a connectivity failure; `manifest unknown` can mean the mirror lacks that exact tag. Do not substitute `latest` or disable TLS verification.

## What base images do not contain

No separate FastAPI or Celery image is needed: build each owning application's image from the Python base with its code and locked dependencies. Workers use the corresponding service image with a different command. This follows the [FastAPI container guidance](https://fastapi.tiangolo.com/deployment/docker/).

The remaining download classes are:

- **Python packages and their transitive dependencies:** `uv`, FastAPI, Uvicorn, Pydantic/settings, SQLAlchemy, Alembic, Psycopg, HTTPX, the Redis client, Celery, aio-pika, PyJWT, cryptography, pwdlib/Argon2, Pillow, python-multipart, email-validator and structlog. Quality tooling includes Ruff, mypy, pytest/asyncio/cov, respx and asgi-lifespan. The roadmap has the proposed direct versions; backend lockfiles and Linux installation validation do not exist yet. Do not claim the baseline list is a complete downloadable wheelhouse. Boto3 is conditional on a later S3 adapter.
- **JavaScript packages:** the exact current web dependency tree is in `apps/web/pnpm-lock.yaml`; the selected package manager is pnpm `11.25.0`. A Windows installation is not a ready Linux container dependency cache. Native dependencies and later UI additions may need additional downloads.
- **Browser test binaries:** current local checks reuse installed Edge. A future Linux Playwright setup needs a matching browser and Linux libraries. No mandatory additional Playwright Docker image is selected for this project.
- **OS packages:** any native compilation or browser runtime packages required by future Dockerfiles need a Debian package cache or an already built image. Do not install a speculative compiler/toolchain on the host.
- **Product media:** licensed exact-SKU photos are separate from Docker images. Current conceptual assets and fonts are already local; they do not establish complete final catalog media.

There is no current requirement for MongoDB, Elasticsearch, MinIO, Kafka, Kubernetes, separate Nginx, pgAdmin, or a prebuilt generic FastAPI image. Architecture changes must be justified before expanding this list.

## Actual offline readiness

Pre-pulling these images reduces future registry traffic but cannot guarantee offline development. After base images are available, the next preparation step is to resolve and lock the backend dependency baseline, cache/download Linux Python wheels and Linux pnpm dependencies, build reusable application/dependency layers while online, then verify a rebuild with network disabled. Record this as dependency preparation, not completed business services. An unresolved package/version or changed dependency can require later network access.

Keep the Docker images and build cache. For a portable backup after all seven pulls succeed, save outside version control (the existing `work/` directory is ignored):

```powershell
New-Item -ItemType Directory -Force work | Out-Null
docker image save --output work/nivaro-base-images.tar node:24.22.1-bookworm-slim caddy:2.11.7 python:3.13.18-slim-bookworm postgres:18.6-bookworm rabbitmq:4.4.0-management redis:8.10.3 axllent/mailpit:v1.32.0
```

Restore on the same target platform with `docker image load --input work/nivaro-base-images.tar`. The archive includes the named base images, not application package caches, build cache, volumes, databases or project files. Sources: [Docker save](https://docs.docker.com/reference/cli/docker/image/save/), [Docker load](https://docs.docker.com/reference/cli/docker/image/load/).
