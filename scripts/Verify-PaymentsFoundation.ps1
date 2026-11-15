param(
    [string]$PaymentsImage = 'nivaro-payments:release',
    [string]$TestImage = 'nivaro-payments:test',
    [string]$IdentityImage = 'nivaro-identity:release'
)
$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
$project = 'nivaro-payments-qa-' + [Guid]::NewGuid().ToString('N').Substring(0, 8)
if ($project -notmatch '^nivaro-payments-qa-[a-f0-9]{8}$') { throw 'Invalid disposable Payments project.' }
$config = @('-p', $project, '-f', "$root/compose.yaml", '-f', "$root/compose.identity-qa.yaml", '-f', "$root/compose.cart-qa.yaml", '-f', "$root/compose.payments.yaml")
$previousImage = $env:NIVARO_PAYMENTS_IMAGE
$previousIdentity = $env:NIVARO_CART_QA_IDENTITY_IMAGE
try {
    & "$PSScriptRoot/Initialize-LocalSecrets.ps1"
    $env:NIVARO_PAYMENTS_IMAGE = $PaymentsImage
    $env:NIVARO_CART_QA_IDENTITY_IMAGE = $IdentityImage
    docker compose @config up -d --no-build --pull never --wait --wait-timeout 90 payments gateway
    if ($LASTEXITCODE -ne 0) { throw 'Disposable Payments stack failed readiness.' }
    docker run --rm --pull never --network "${project}_default" `
        -e "PAYMENTS_DB_HOST=$project-postgres-1" -e PAYMENTS_E2E=1 -e PYTHONPATH=/app/src `
        -v "${root}/work/secrets/payments_db_password.txt:/run/secrets/payments_db_password:ro" `
        -v "${root}/work/secrets/orders_client_secret.txt:/run/secrets/orders_client_secret:ro" `
        $TestImage sh -ec 'alembic upgrade head && alembic check && ruff check . && ruff format --check . && mypy src && pytest -q'
    if ($LASTEXITCODE -ne 0) { throw 'Payments foundation checks failed.' }
    Write-Output 'Verified payment simulation, service scope, database isolation and concurrent idempotency.'
} catch {
    docker compose @config logs --no-color --tail 35 payments identity gateway
    throw
} finally {
    docker compose @config down --volumes
    $env:NIVARO_PAYMENTS_IMAGE = $previousImage
    $env:NIVARO_CART_QA_IDENTITY_IMAGE = $previousIdentity
}
