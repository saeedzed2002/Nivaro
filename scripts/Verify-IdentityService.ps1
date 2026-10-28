param([string]$TestImage = '')
$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
$source = Join-Path $root 'services/identity'
if (-not $TestImage -and -not (Test-Path (Join-Path $source '.venv/bin/pytest'))) { throw 'Prepare identity dependencies first.' }
$suffix = [Guid]::NewGuid().ToString('N').Substring(0, 10)
$network = "nivaro-identity-service-$suffix"
$postgres = "nivaro-identity-pg-$suffix"
$redis = "nivaro-identity-state-$suffix"
$created = @()
$networkCreated = $false
try {
    docker network create --internal $network | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'Test network creation failed.' }
    $networkCreated = $true
    $secretMounts = @()
    foreach ($name in @('postgres_admin_password','identity_db_password','catalog_db_password','redis_state_password')) {
        $secretMounts += @('-v', "${root}/work/secrets/${name}.txt:/run/secrets/${name}:ro")
    }
    docker run --rm -d --pull never --name $postgres --network $network @secretMounts `
        --tmpfs /var/lib/postgresql -e POSTGRES_PASSWORD_FILE=/run/secrets/postgres_admin_password -e POSTGRES_USER=postgres `
        -v "${root}/infra/postgres/10-catalog.sh:/docker-entrypoint-initdb.d/10-catalog.sh:ro" `
        -v "${root}/infra/postgres/20-identity.sh:/docker-entrypoint-initdb.d/20-identity.sh:ro" `
        postgres:18.6-bookworm@sha256:bbf83594798e144bff365a9c191c5d779f181fb3135902064ab8ff11918020fc | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'Temporary PostgreSQL failed.' }
    $created += $postgres
    docker run --rm -d --pull never --name $redis --network $network @secretMounts `
        -v "${root}/infra/redis/start-state.sh:/start-state.sh:ro" `
        redis:8.10.3@sha256:0c257ce8b2f31f9f7595f587edf8ac259a248ba3ced82badc8c7aa826a85224f sh /start-state.sh | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'Temporary Redis failed.' }
    $created += $redis
    $ready = $false
    for ($attempt=0; $attempt -lt 30; $attempt++) {
        docker exec $postgres pg_isready -h 127.0.0.1 -U postgres | Out-Null
        if ($LASTEXITCODE -eq 0) { $ready=$true; break }
        Start-Sleep -Milliseconds 500
    }
    if (-not $ready) { throw 'Temporary PostgreSQL readiness timed out.' }
    $runtime = if ($TestImage) { $TestImage } else { 'python:3.13.18-slim-bookworm' }
    $sourceMount = if ($TestImage) { @() } else { @('-v',"${source}:/app") }
    docker run --rm --pull never --network $network @secretMounts @sourceMount `
        -v "${root}/contracts:/contracts:ro" -w /app `
        -e "IDENTITY_DB_HOST=$postgres" -e "IDENTITY_REDIS_HOST=$redis" `
        -e IDENTITY_SERVICE_TESTS=1 -e "IDENTITY_TEST_REDIS_URL=redis://${redis}:6379/0" `
        -e IDENTITY_TEST_REDIS_PASSWORD_FILE=/run/secrets/redis_state_password `
        $runtime `
        sh -c '.venv/bin/alembic upgrade head && .venv/bin/alembic upgrade head && .venv/bin/alembic check && .venv/bin/ruff check . && .venv/bin/ruff format --check . && .venv/bin/mypy src && .venv/bin/pytest -q && .venv/bin/python -m nivaro_identity.export_openapi /contracts/openapi/identity.json --check'
    if ($LASTEXITCODE -ne 0) { throw 'Identity service checks failed.' }
    Write-Output 'Identity migrations, isolated database/Redis API checks and source checks passed.'
} finally {
    foreach ($container in $created) { docker stop $container | Out-Null }
    if ($networkCreated) { docker network rm $network | Out-Null }
}
