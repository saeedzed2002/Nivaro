$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
$source = Join-Path $root 'services/identity'
if (-not (Test-Path -LiteralPath (Join-Path $source 'uv.lock')) -or
    -not (Test-Path -LiteralPath (Join-Path $source '.venv/bin/pytest'))) {
    throw 'Run Prepare-IdentityDependencies.ps1 successfully first. No verified Linux identity environment exists yet.'
}
$suffix = [Guid]::NewGuid().ToString('N').Substring(0, 10)
$network = "nivaro-identity-check-$suffix"
$container = "nivaro-identity-redis-$suffix"
$networkCreated = $false
$containerCreated = $false
try {
    docker network create --internal $network | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'Unable to create isolated test network.' }
    $networkCreated = $true
    docker run --rm -d --pull never --network $network --name $container `
        redis:8.10.3 redis-server --save '' --appendonly no `
        --maxmemory 64mb --maxmemory-policy noeviction | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'Unable to start disposable Redis.' }
    $containerCreated = $true
    $ready = $false
    for ($attempt = 0; $attempt -lt 10; $attempt++) {
        $reply = docker exec $container redis-cli ping
        if ($LASTEXITCODE -eq 0 -and $reply -eq 'PONG') { $ready = $true; break }
        Start-Sleep -Milliseconds 500
    }
    if (-not $ready) { throw 'Disposable Redis did not become ready.' }
    docker run --rm --pull never --network $network `
        -v "${source}:/app" -w /app `
        -e "IDENTITY_TEST_REDIS_URL=redis://${container}:6379/0" `
        python:3.13.18-slim-bookworm `
        sh -c '.venv/bin/ruff check . && .venv/bin/ruff format --check . && .venv/bin/mypy src && .venv/bin/pytest -q'
    if ($LASTEXITCODE -ne 0) { throw 'Identity foundation verification failed.' }
    Write-Output 'Selected Linux foundation checks passed. API, sessions, frontend and P03 acceptance remain separate gates.'
} finally {
    if ($containerCreated) { docker stop $container | Out-Null }
    if ($networkCreated) { docker network rm $network | Out-Null }
}
