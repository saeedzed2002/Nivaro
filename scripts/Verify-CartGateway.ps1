param(
    [string]$CartImage = 'nivaro-cart:release',
    [string]$CatalogImage = 'nivaro-catalog:release',
    [string]$IdentityImage = 'nivaro-identity:release'
)
$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
$project = 'nivaro-p05-qa-' + [Guid]::NewGuid().ToString('N').Substring(0, 8)
$config = @('compose', '-p', $project, '-f', "$root/compose.yaml", '-f', "$root/compose.identity-qa.yaml", '-f', "$root/compose.cart-qa.yaml")
$images = @{
    NIVARO_CART_IMAGE = $CartImage
    NIVARO_CART_QA_CATALOG_IMAGE = $CatalogImage
    NIVARO_CART_QA_IDENTITY_IMAGE = $IdentityImage
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
} finally {
    if ($started) {
        if ($project -notmatch '^nivaro-p05-qa-[a-f0-9]{8}$') { throw 'Unsafe cleanup target.' }
        docker @config down --volumes
    }
    foreach ($name in $saved.Keys) { [Environment]::SetEnvironmentVariable($name, $saved[$name]) }
}
