param(
    [string]$OrdersImage = 'nivaro-orders:release',
    [string]$TestImage = 'nivaro-orders:test',
    [string]$CatalogImage = 'nivaro-catalog:release',
    [switch]$WithCatalog,
    [switch]$WithEvents
)
$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
$project = 'nivaro-orders-qa-' + [Guid]::NewGuid().ToString('N').Substring(0, 8)
$config = @('-p', $project, '-f', "$root/compose.yaml", '-f', "$root/compose.identity-qa.yaml", '-f', "$root/compose.orders.yaml")
$previousImage = $env:NIVARO_ORDERS_IMAGE
$previousCatalogImage = $env:NIVARO_CART_QA_CATALOG_IMAGE
$previousPublisherImage = $env:NIVARO_EVENT_CATALOG_IMAGE
if ($project -notmatch '^nivaro-orders-qa-[a-f0-9]{8}$') { throw 'Unsafe test project.' }
if ($WithEvents) {
    $WithCatalog = $true
    $config += @('-f', "$root/compose.media.yaml", '-f', "$root/compose.cart-qa.yaml", '-f', "$root/compose.events.yaml")
}
try {
    & "$PSScriptRoot/Initialize-LocalSecrets.ps1"
    $env:NIVARO_ORDERS_IMAGE = $OrdersImage
    $services = @('orders')
    if ($WithCatalog) { $services += @('catalog', 'identity', 'redis-cache') }
    if ($WithEvents) {
        & "$PSScriptRoot/Initialize-MediaSecrets.ps1"
        $env:NIVARO_CART_QA_CATALOG_IMAGE = $CatalogImage
        $env:NIVARO_EVENT_CATALOG_IMAGE = $CatalogImage
        $services += @('catalog-event-publisher', 'orders-expiry-consumer')
    }
    docker compose @config up -d --no-build --pull never --wait --wait-timeout 60 @services
    if ($LASTEXITCODE -ne 0) { throw 'Disposable Orders stack failed readiness.' }
    $integration = @()
    if ($WithCatalog) {
        if ($project -notmatch '^nivaro-orders-qa-[a-f0-9]{8}$') { throw 'Unsafe catalog fixture target.' }
        Get-Content "$PSScriptRoot/cart-browser-fixture.sql" -Raw | docker compose @config exec -T postgres psql -v ON_ERROR_STOP=1 -U postgres -d nivaro_catalog
        if ($LASTEXITCODE -ne 0) { throw 'Disposable catalog stock fixture failed.' }
        $integration = @('-e', 'ORDERS_CATALOG_E2E=1', '-v', "${root}/work/secrets/orders_client_secret.txt:/run/secrets/orders_client_secret:ro")
    }
    if ($WithEvents) {
        $integration += @('-e', 'ORDERS_EVENT_E2E=1',
            '-v', "${root}/work/secrets/catalog_db_password.txt:/run/secrets/catalog_db_password:ro",
            '-v', "${root}/work/secrets/catalog_event_broker_password.txt:/run/secrets/catalog_event_broker_password:ro")
    }
    docker run --rm --pull never --network "${project}_default" -e "ORDERS_DB_HOST=$project-postgres-1" -e ORDERS_DISPOSABLE_TESTS=1 -e PYTHONPATH=/app/src -v "${root}/work/secrets/orders_db_password.txt:/run/secrets/orders_db_password:ro" @integration $TestImage sh -ec 'alembic upgrade head && alembic check && ruff check . && ruff format --check . && mypy src && pytest -q'
    if ($LASTEXITCODE -ne 0) { throw 'Orders foundation checks failed.' }
    if ($WithEvents) {
        $deadLettered = $false
        foreach ($attempt in 1..10) {
            $queues = docker compose @config exec -T rabbitmq rabbitmqctl -q list_queues -p commerce-events name messages --formatter json | ConvertFrom-Json
            if ($LASTEXITCODE -ne 0) { throw 'Could not inspect disposable event queues.' }
            $dead = $queues | Where-Object name -EQ 'orders.inventory.reservation.expired.v1.error'
            $live = $queues | Where-Object name -EQ 'orders.inventory.reservation.expired.v1'
            if ($dead.messages -eq 1 -and $live.messages -eq 0) { $deadLettered = $true; break }
            Start-Sleep -Seconds 1
        }
        if (-not $deadLettered) { throw 'Event queue did not drain into the expected dead-letter queue.' }
        Write-Output 'RabbitMQ routed the malformed event to the durable error queue.'
    }
    Write-Output 'Orders release readiness, migrations, totals, coupon concurrency and reservation checks passed.'
} catch {
    if ($WithEvents) {
        docker compose @config logs --no-color --tail 40 catalog-event-publisher orders-expiry-consumer rabbitmq
    }
    throw
} finally {
    docker compose @config down --volumes
    $env:NIVARO_ORDERS_IMAGE = $previousImage
    $env:NIVARO_CART_QA_CATALOG_IMAGE = $previousCatalogImage
    $env:NIVARO_EVENT_CATALOG_IMAGE = $previousPublisherImage
}
