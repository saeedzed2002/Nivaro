param([string]$TestImage = '')
$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
$suffix = [Guid]::NewGuid().ToString('N').Substring(0, 10)
$network = "nivaro-cart-test-$suffix"
$postgres = "nivaro-cart-pg-$suffix"
$networkCreated = $false
$started = $false
try {
    docker network create --internal $network | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'Cart test network failed.' }
    $networkCreated = $true
    $secrets = @()
    foreach ($name in @('postgres_admin_password','catalog_db_password','identity_db_password','cart_db_password')) {
        $secrets += @('-v', "${root}/work/secrets/${name}.txt:/run/secrets/${name}:ro")
    }
    docker run --rm -d --pull never --network $network --name $postgres --tmpfs /var/lib/postgresql `
        @secrets -e POSTGRES_USER=postgres -e POSTGRES_PASSWORD_FILE=/run/secrets/postgres_admin_password `
        -v "${root}/infra/postgres/10-catalog.sh:/docker-entrypoint-initdb.d/10-catalog.sh:ro" `
        -v "${root}/infra/postgres/20-identity.sh:/docker-entrypoint-initdb.d/20-identity.sh:ro" `
        -v "${root}/infra/postgres/30-cart.sh:/docker-entrypoint-initdb.d/30-cart.sh:ro" `
        postgres:18.6-bookworm@sha256:bbf83594798e144bff365a9c191c5d779f181fb3135902064ab8ff11918020fc | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'Temporary cart PostgreSQL failed.' }
    $started = $true
    $ready = $false
    foreach ($attempt in 1..30) {
        if (-not (docker ps -q --filter "name=^/${postgres}$")) { throw 'Temporary cart database exited during initialization.' }
        docker exec $postgres pg_isready -h 127.0.0.1 -U postgres | Out-Null
        if ($LASTEXITCODE -eq 0) { $ready=$true; break }
        Start-Sleep -Milliseconds 500
    }
    if (-not $ready) { throw 'Cart test database readiness timed out.' }
    $runtime = if ($TestImage) { $TestImage } else { 'python:3.13.18-slim-bookworm' }
    $source = if ($TestImage) { @() } else { @('-v', "${root}/services/cart:/app") }
    docker run --rm --pull never --network $network @secrets @source -w /app -e PYTHONPATH=src `
        -v "${root}/contracts:/contracts:ro" `
        -e "CART_DB_HOST=$postgres" -e CART_DISPOSABLE_TESTS=1 $runtime `
        sh -ec '.venv/bin/alembic upgrade head && .venv/bin/alembic upgrade head && .venv/bin/alembic check && .venv/bin/ruff check . && .venv/bin/ruff format --check . && .venv/bin/mypy src && .venv/bin/pytest -q && .venv/bin/python -m nivaro_cart.export_openapi /contracts/openapi/cart.json --check'
    if ($LASTEXITCODE -ne 0) { throw 'Cart foundation checks failed.' }
    Write-Output 'Cart migrations, schema, ownership, versioned mutations, concurrency, limits, isolation and health checks passed.'
} finally {
    if ($started -and (docker ps -q --filter "name=^/${postgres}$")) { docker stop $postgres | Out-Null }
    if ($networkCreated) { docker network rm $network | Out-Null }
}
