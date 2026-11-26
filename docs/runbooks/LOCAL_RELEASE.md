# Run the local release from a clean checkout

Use a fresh checkout of the private repository, Docker Desktop in Linux-container mode, Docker Compose v2 and PowerShell 7.4 or later. Run the following from the checkout root. Docker images use pinned base references. Building the application also requires access to the npm and PyPI registries to install locked dependencies.

The complete release includes the storefront, six application services, PostgreSQL, Redis, RabbitMQ and background workers. The default host binding is `127.0.0.1:8080`. If an existing development preview uses it, add the `work/restore-port.yaml` loopback and origin override shown in [the restore guide](BACKUP_RESTORE.md#restore-to-an-isolated-project) as the final file in `$files` after initializing the secrets. With that override, open `http://127.0.0.1:8084`.

## Build and start

```powershell
$ErrorActionPreference = 'Stop'
$PSNativeCommandUseErrorActionPreference = $true
$project = 'nivaro-release'
$files = @('-f', 'compose.yaml', '-f', 'compose.media.yaml', '-f', 'compose.orders.yaml',
    '-f', 'compose.events.yaml', '-f', 'compose.payments.yaml', '-f', 'compose.payment-events.yaml',
    '-f', 'compose.support.yaml')
./scripts/Initialize-LocalSecrets.ps1
./scripts/Initialize-MediaSecrets.ps1
docker compose -p $project @files config --images
docker compose -p $project @files build web catalog-init identity-init cart-init orders-init payments-init support-init
docker compose -p $project @files up -d --no-build --wait --wait-timeout 120
docker compose -p $project @files ps --all
```

Open `http://localhost:8080/fa` and `http://localhost:8080/en`. Check that the web container and all six application services are healthy. Initialization jobs can exit with code 0 because they perform a finite task. The initial Catalog seed is research data. Payment checkout and OTP are local simulation paths. Staff sign-in requires an explicit administrator bootstrap through the [Identity operator guide](../../services/identity/README.md). Use only synthetic data for this release exercise.

## Stop, restart and diagnose

```powershell
docker compose -p $project @files stop
docker compose -p $project @files up -d --no-build --pull never --wait --wait-timeout 120
docker compose -p $project @files ps --all
docker compose -p $project @files logs --tail 100 gateway web catalog-init identity-init orders-init payments-init support-init
```

- For a dependency download failure, identify the registry and failing package or pinned image in the build output. Check registry access from Docker and use the documented [pinned image preparation](../DOWNLOAD_PREPARATION.md) when a base image is unavailable locally. Retry with the lockfiles and registry checks enabled.
- For a port conflict, use the separate loopback binding above and verify its host URL. Only the gateway should need a host port.
- For a failed migration or seed, inspect the corresponding initialization log and recover using the [backup and rollback guide](BACKUP_RESTORE.md). Keep the existing named volumes and credential files when restarting the same project.
- For local source synchronisation and browser hot reload, use the [development launcher](../../README.md#local-development). The release command above runs the images built from the selected checkout.

See [incident procedures](INCIDENTS.md) for staff recovery, signing keys, media, payments and Support.
