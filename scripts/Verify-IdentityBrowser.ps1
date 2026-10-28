# Fresh isolated browser stack: never reset the owner's accounts or OTP limits.
$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
$project = 'nivaro-p03-qa-' + [Guid]::NewGuid().ToString('N').Substring(0, 8)
$compose = @('compose','-p',$project,'-f',"$root/compose.yaml",'-f',"$root/compose.identity-qa.yaml")
$saved = @{}
foreach ($name in @('TEST_BASE_URL','NIVARO_IDENTITY_QA_PROJECT','COREPACK_ENABLE_NETWORK')) { $saved[$name] = [Environment]::GetEnvironmentVariable($name) }
try {
    docker @compose up -d --no-build --pull never --wait --wait-timeout 100
    if ($LASTEXITCODE -ne 0) { throw 'Isolated browser stack failed readiness.' }
    $env:TEST_BASE_URL = 'http://127.0.0.1:8082'
    $env:NIVARO_IDENTITY_QA_PROJECT = $project
    $env:COREPACK_ENABLE_NETWORK = '0'
    Push-Location "$root/apps/web"
    try {
        corepack pnpm exec playwright test tests/identity.spec.ts
        if ($LASTEXITCODE -ne 0) { throw 'Identity browser checks failed.' }
    } finally { Pop-Location }
} finally {
    docker @compose down
    foreach ($name in $saved.Keys) { [Environment]::SetEnvironmentVariable($name, $saved[$name]) }
}
