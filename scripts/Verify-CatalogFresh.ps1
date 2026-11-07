param([string]$CatalogImage = 'nivaro-catalog:release')
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path $PSScriptRoot -Parent
$probeName = 'nivaro-p02-fresh-postgres'
$pgImage = 'postgres:18.6-bookworm@sha256:bbf83594798e144bff365a9c191c5d779f181fb3135902064ab8ff11918020fc'
$pythonImage = 'python:3.13.18-slim-bookworm@sha256:93498f36dc7e24ef233bfdf6cc17d4b8bd32d94ee737143e906460d5f5a914c5'
if (docker ps -aq --filter "name=^/${probeName}$") { throw 'Probe container already exists; refusing to replace it.' }
$started = $false
try {
    docker run --rm -d --pull never --name $probeName --network nivaro_default --tmpfs /var/lib/postgresql `
      -e POSTGRES_USER=postgres -e POSTGRES_PASSWORD_FILE=/run/secrets/postgres_admin_password `
      -v "${projectRoot}/work/secrets/postgres_admin_password.txt:/run/secrets/postgres_admin_password:ro" `
      -v "${projectRoot}/work/secrets/catalog_db_password.txt:/run/secrets/catalog_db_password:ro" `
      -v "${projectRoot}/infra/postgres/10-catalog.sh:/docker-entrypoint-initdb.d/10-catalog.sh:ro" $pgImage
    if ($LASTEXITCODE -ne 0) { throw 'Fresh database did not start.' }
    $started = $true
    $ready = $false
    foreach ($attempt in 1..30) {
        # TCP avoids reporting the entrypoint's temporary Unix-socket server as ready.
        docker exec $probeName pg_isready -h 127.0.0.1 -U postgres -d nivaro_catalog 2>$null | Out-Null
        if ($LASTEXITCODE -eq 0) { $ready = $true; break }
        Start-Sleep -Seconds 1
    }
    if (-not $ready) { throw 'Fresh database readiness timed out.' }
    docker run --rm --pull never --network nivaro_default -e "CATALOG_DB_HOST=$probeName" `
      -v "${projectRoot}/work/secrets/catalog_db_password.txt:/run/secrets/catalog_db_password:ro" `
      $CatalogImage sh -c 'alembic upgrade head && python -m nivaro_catalog.infrastructure.seed && python -m nivaro_catalog.infrastructure.seed && alembic check'
    if ($LASTEXITCODE -ne 0) { throw 'Fresh migrations or repeatable seed failed.' }
    docker run --rm --pull never --network nivaro_default -e "CATALOG_DB_HOST=$probeName" -e CATALOG_DISPOSABLE_TESTS=1 `
      -v "${projectRoot}/services/catalog:/app" -w /app `
      -v "${projectRoot}/work/secrets/catalog_db_password.txt:/run/secrets/catalog_db_password:ro" `
      $pythonImage /app/.venv/bin/pytest -q
    if ($LASTEXITCODE -ne 0) { throw 'Fresh database tests failed.' }
} finally {
    if ($started) { docker stop $probeName | Out-Null }
}
Write-Output 'Fresh migration, repeatable seed and tests passed; only disposable tmpfs database stopped.'
