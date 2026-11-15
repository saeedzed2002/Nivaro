param(
    [string]$OrdersImage = 'nivaro-orders:release',
    [string]$TestImage = 'nivaro-orders:test',
    [switch]$WithCatalog
)
$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
$project = 'nivaro-orders-qa-' + [Guid]::NewGuid().ToString('N').Substring(0, 8)
$config = @('-p', $project, '-f', "$root/compose.yaml", '-f', "$root/compose.identity-qa.yaml", '-f', "$root/compose.orders.yaml")
$previousImage = $env:NIVARO_ORDERS_IMAGE
try {
    & "$PSScriptRoot/Initialize-LocalSecrets.ps1"
    $env:NIVARO_ORDERS_IMAGE = $OrdersImage
    $services = @('orders')
    if ($WithCatalog) { $services += @('catalog', 'identity', 'redis-cache') }
    docker compose @config up -d --no-build --pull never --wait --wait-timeout 60 @services
    if ($LASTEXITCODE -ne 0) { throw 'Disposable Orders stack failed readiness.' }
    $integration = @()
    if ($WithCatalog) {
        if ($project -notmatch '^nivaro-orders-qa-[a-f0-9]{8}$') { throw 'Unsafe catalog fixture target.' }
        Get-Content "$PSScriptRoot/cart-browser-fixture.sql" -Raw | docker compose @config exec -T postgres psql -v ON_ERROR_STOP=1 -U postgres -d nivaro_catalog
        if ($LASTEXITCODE -ne 0) { throw 'Disposable catalog stock fixture failed.' }
        $integration = @('-e', 'ORDERS_CATALOG_E2E=1', '-v', "${root}/work/secrets/orders_client_secret.txt:/run/secrets/orders_client_secret:ro")
    }
    docker run --rm --pull never --network "${project}_default" -e "ORDERS_DB_HOST=$project-postgres-1" -e ORDERS_DISPOSABLE_TESTS=1 -e PYTHONPATH=/app/src -v "${root}/work/secrets/orders_db_password.txt:/run/secrets/orders_db_password:ro" @integration $TestImage sh -ec 'alembic upgrade head && alembic check && ruff check . && ruff format --check . && mypy src && pytest -q'
    if ($LASTEXITCODE -ne 0) { throw 'Orders foundation checks failed.' }
    Write-Output 'Orders release readiness, migrations, totals, coupon concurrency and reservation checks passed.'
} finally {
    docker compose @config down
    $env:NIVARO_ORDERS_IMAGE = $previousImage
}
