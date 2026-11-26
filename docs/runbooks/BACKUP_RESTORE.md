# Release backup, restore and rollback

The backup contains six PostgreSQL custom-format dumps, Catalog and Identity media archives, and a SHA-256 manifest. The archives include originals and generated images. Restore preserves database object ownership and file ownership and permissions. Keep the release revision, image tags or digests, configuration and secrets in separately protected storage. Restrict and encrypt stored copies because the bundle contains customer information and private avatars. Restore only a bundle from a trusted source. The manifest detects corruption and requires protection alongside the data. See [pg_dump](https://www.postgresql.org/docs/18/app-pgdump.html) and [pg_restore](https://www.postgresql.org/docs/18/app-pgrestore.html).

Redis caches and push notifications rebuild from application state. Broker queues and PostgreSQL role passwords are outside the bundle. Use a maintenance window for consistency across the independent databases and file volumes. A message that was published to RabbitMQ and has yet to be applied by its consumer can require reconciliation after a restore. Carry forward outstanding event IDs and failed queue observations from the maintenance window.

## Back up a stopped release

Use PowerShell 7 and Docker Compose v2 from the release checkout. The project name must match the already running release. The source needs its existing database and media volumes and the locally available pinned Python image.

```powershell
$files = @('-f', 'compose.yaml', '-f', 'compose.media.yaml', '-f', 'compose.orders.yaml',
    '-f', 'compose.events.yaml', '-f', 'compose.payments.yaml', '-f', 'compose.payment-events.yaml',
    '-f', 'compose.support.yaml')
$source = 'nivaro-release'
docker compose -p $source @files stop gateway
foreach ($vhost in @('commerce-events', 'catalog-media', 'identity-media')) {
    docker compose -p $source @files exec -T rabbitmq rabbitmqctl -q list_queues -p $vhost name messages_ready messages_unacknowledged
    if ($LASTEXITCODE -ne 0) { throw "Could not read queues for $vhost" }
}
```

Stop direct database clients too. Leave workers up while outstanding work drains. Recheck ready and unacknowledged counts, and investigate persistent backlog, error queues, pending outbox deliveries and ambiguous payment attempts before taking the snapshot. Record any work still requiring reconciliation. Then stop writers and take the backup. Stop on any command failure.

```powershell
docker compose -p $source @files stop
docker compose -p $source @files up -d --no-build --pull never --wait postgres
$bundle = Join-Path (Get-Location) ('work/backups/release-' + (Get-Date -Format 'yyyyMMdd-HHmmss'))
./scripts/Manage-ReleaseBackup.ps1 Backup $source $bundle
Get-Content -LiteralPath (Join-Path $bundle 'manifest.json')
docker compose -p $source @files up -d --no-build --pull never --wait
```

Record the backup time and source revision. Copy the complete bundle out of the Compose host to protected storage. Only a backup with a completed manifest and matching files is ready for a restore test.

## Restore to an isolated project

Start in a separate clean checkout of the source release revision with its release images available. Define `$files` as above, then initialize local credentials in this checkout. Use a new Compose project name and an unused loopback port. Keep the gateway isolated from users and external providers until verification finishes.

```powershell
./scripts/Initialize-LocalSecrets.ps1
./scripts/Initialize-MediaSecrets.ps1
@'
services:
  gateway:
    ports: !override
      - '127.0.0.1:8084:8080'
'@ | Set-Content -LiteralPath work/restore-port.yaml -Encoding utf8NoBOM
$files += @('-f', 'work/restore-port.yaml')
$target = 'nivaro-restore'
$bundle = (Resolve-Path 'D:/backups/nivaro/release-YYYYMMDD-HHMMSS').Path
docker compose -p $target @files up -d --no-build --pull never --wait postgres
foreach ($service in @('identity-db-init', 'cart-db-init', 'orders-db-init', 'payments-db-init', 'support-db-init')) {
    docker compose -p $target @files run --rm --no-deps --pull never $service
    if ($LASTEXITCODE -ne 0) { throw "Could not initialize $service" }
}
docker compose -p $target @files create --no-build catalog-media-init identity-media-init
./scripts/Manage-ReleaseBackup.ps1 Restore $target $bundle
docker compose -p $target @files up -d --no-build --pull never --wait
```

The operation rejects a bundle from the selected project, invalid checksums and populated destinations. A database restore commits in one transaction per database. If any later component fails, retain the source bundle, inspect the failure and restart against a fresh empty target. Use a fresh login when verifying a destination initialized with new signing secrets. Coordinate administrator access and secret rotation with the release operator.

Check all six service health endpoints through their Compose containers and both storefront locales through the gateway. Compare known product and order records, the payment amount and currency, support message history, and downloaded media hashes with the source evidence. Verify direct access to private media and conversations returns HTTP 401 without a session. For a repeatable synthetic exercise, run `./scripts/Verify-ReleaseBackup.ps1` with the intended local release images. The drill provisions its own two projects and uses loopback port 8084 by default.

## Roll back a release

Before migration, retain the previous release revision, images, configuration and a verified database/media bundle. Check old application compatibility against the new schema on the isolated restored target. If compatible, stop incoming traffic, switch to the pinned previous images without running incompatible migrations, and verify health, reads and authorized writes before reopening traffic.

If compatibility fails, restore the pre-migration bundle into a fresh isolated project and verify it before switching traffic. Record the write gap from backup time to cutover and reconcile late payments, order events and media writes against retained source evidence. Use the [payment reconciliation procedure](../../services/payments/README.md) and the [Catalog media operations](../../services/catalog/README.md#p04-catalog-media-runtime) procedures with the affected record IDs. A synthetic drill demonstrates recovery behavior. Measure recovery time and achievable data loss against representative data before declaring service objectives met.
