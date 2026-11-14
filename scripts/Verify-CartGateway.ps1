param(
    [string]$CartImage = 'nivaro-cart:release',
    [string]$CatalogImage = 'nivaro-catalog:release',
    [string]$IdentityImage = 'nivaro-identity:release',
    [string]$WebImage = 'nivaro-web:release',
    [switch]$HostWeb,
    [switch]$Browser
)
$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
$project = 'nivaro-p05-qa-' + [Guid]::NewGuid().ToString('N').Substring(0, 8)
$config = @('compose', '-p', $project, '-f', "$root/compose.yaml", '-f', "$root/compose.identity-qa.yaml", '-f', "$root/compose.cart-qa.yaml")
$images = @{
    NIVARO_CART_IMAGE = $CartImage
    NIVARO_CART_QA_CATALOG_IMAGE = $CatalogImage
    NIVARO_CART_QA_IDENTITY_IMAGE = $IdentityImage
    NIVARO_CART_QA_WEB_IMAGE = $WebImage
    NIVARO_CART_QA_WEB_UPSTREAM = $(if ($HostWeb) { 'host.docker.internal:8085' } else { 'web:3000' })
}
$saved = @{}
$started = $false
try {
    foreach ($name in $images.Keys) {
        $saved[$name] = [Environment]::GetEnvironmentVariable($name)
        [Environment]::SetEnvironmentVariable($name, $images[$name])
    }
    & "$PSScriptRoot/Initialize-LocalSecrets.ps1"
    $started = $true
    docker @config up -d --no-build --pull never --wait --wait-timeout 100
    if ($LASTEXITCODE -ne 0) { throw 'Disposable cart stack failed readiness.' }
    node "$PSScriptRoot/verify-cart-gateway.mjs"
    if ($LASTEXITCODE -ne 0) { throw 'Cart gateway check failed.' }
    if ($Browser) {
        if ($project -notmatch '^nivaro-p05-qa-[a-f0-9]{8}$') { throw 'Unsafe fixture target.' }
        Get-Content "$PSScriptRoot/cart-browser-fixture.sql" -Raw | docker @config exec -T postgres psql -v ON_ERROR_STOP=1 -U postgres -d nivaro_catalog
        if ($LASTEXITCODE -ne 0) { throw 'Disposable catalog fixture failed.' }
        foreach ($name in @('TEST_BASE_URL','NIVARO_CART_QA_PROJECT')) { $saved[$name] = [Environment]::GetEnvironmentVariable($name) }
        $env:TEST_BASE_URL = 'http://127.0.0.1:8082'
        $env:NIVARO_CART_QA_PROJECT = $project
        Push-Location "$root/apps/web"
        try {
            node node_modules/@playwright/test/cli.js test tests/cart-gateway.spec.ts
            if ($LASTEXITCODE -ne 0) { throw 'Cart browser integration failed.' }
        } finally { Pop-Location }
    }
} finally {
    if ($started) {
        if ($project -notmatch '^nivaro-p05-qa-[a-f0-9]{8}$') { throw 'Unsafe cleanup target.' }
        docker @config down --volumes
    }
    foreach ($name in $saved.Keys) { [Environment]::SetEnvironmentVariable($name, $saved[$name]) }
}
