param(
    [string]$OrdersImage = 'nivaro-orders:release',
    [string]$TestImage = 'nivaro-orders:test'
)
$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
$project = 'nivaro-orders-qa-' + [Guid]::NewGuid().ToString('N').Substring(0, 8)
$config = @('-p', $project, '-f', "$root/compose.yaml", '-f', "$root/compose.identity-qa.yaml", '-f', "$root/compose.orders.yaml")
$previousImage = $env:NIVARO_ORDERS_IMAGE
try {
    & "$PSScriptRoot/Initialize-LocalSecrets.ps1"
    $env:NIVARO_ORDERS_IMAGE = $OrdersImage
    docker compose @config up -d --no-build --pull never --wait --wait-timeout 60 orders
    if ($LASTEXITCODE -ne 0) { throw 'Disposable Orders stack failed readiness.' }
    docker run --rm --pull never --network "${project}_default" -e "ORDERS_DB_HOST=$project-postgres-1" -e ORDERS_DISPOSABLE_TESTS=1 -e PYTHONPATH=/app/src -v "${root}/work/secrets/orders_db_password.txt:/run/secrets/orders_db_password:ro" $TestImage sh -ec 'alembic upgrade head && alembic check && ruff check . && ruff format --check . && mypy src && pytest -q'
    if ($LASTEXITCODE -ne 0) { throw 'Orders foundation checks failed.' }
    Write-Output 'Orders release readiness, migrations, role isolation, totals, snapshots and coupon concurrency passed.'
} finally {
    docker compose @config down
    $env:NIVARO_ORDERS_IMAGE = $previousImage
}
