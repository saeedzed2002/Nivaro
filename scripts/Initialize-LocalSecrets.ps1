$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
$directory = Join-Path $root 'work/secrets'
New-Item -ItemType Directory -Path $directory -Force | Out-Null
foreach ($name in @('postgres_admin_password', 'catalog_db_password')) {
    $path = Join-Path $directory "$name.txt"
    if (-not (Test-Path -LiteralPath $path)) {
        $bytes = [System.Security.Cryptography.RandomNumberGenerator]::GetBytes(48)
        [IO.File]::WriteAllText($path, [Convert]::ToBase64String($bytes), [Text.UTF8Encoding]::new($false))
    }
}
Write-Output 'Local database secret files exist. Existing values were preserved; no values were printed.'
