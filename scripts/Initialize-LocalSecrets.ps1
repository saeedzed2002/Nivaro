$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
$directory = Join-Path $root 'work/secrets'
New-Item -ItemType Directory -Path $directory -Force | Out-Null
foreach ($name in @('postgres_admin_password', 'catalog_db_password', 'cart_db_password', 'identity_db_password', 'redis_state_password', 'redis_cache_password', 'otp_pepper', 'catalog_identity_service_key')) {
    $path = Join-Path $directory "$name.txt"
    if (-not (Test-Path -LiteralPath $path)) {
        $bytes = [System.Security.Cryptography.RandomNumberGenerator]::GetBytes(48)
        [IO.File]::WriteAllText($path, [Convert]::ToBase64String($bytes), [Text.UTF8Encoding]::new($false))
    }
}
$signingKey = Join-Path $directory 'identity_signing_key.pem'
if (-not (Test-Path -LiteralPath $signingKey)) {
    $rsa = [System.Security.Cryptography.RSA]::Create(3072)
    try { [IO.File]::WriteAllText($signingKey, $rsa.ExportPkcs8PrivateKeyPem(), [Text.UTF8Encoding]::new($false)) }
    finally { $rsa.Dispose() }
}
Write-Output 'Local database secret files exist. Existing values were preserved; no values were printed.'
