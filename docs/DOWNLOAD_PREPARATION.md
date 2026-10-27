# Download preparation for the planned local stack

Verified on 2026-10-27 against the canonical English roadmap and Docker Hub tag API. All seven tags below were reported active with a `linux/amd64` variant. This metadata check did not download layers, validate mirror availability, establish digests of local images or prove runtime compatibility.

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
