$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
$directory = Join-Path $root 'work/secrets'
New-Item -ItemType Directory -Path $directory -Force | Out-Null
$users = @()
$permissions = @()
$vhosts = @()
foreach ($service in @('catalog', 'identity')) {
    $path = Join-Path $directory "${service}_media_broker_password.txt"
    if (-not (Test-Path -LiteralPath $path)) {
        [IO.File]::WriteAllText($path, [Convert]::ToBase64String([Security.Cryptography.RandomNumberGenerator]::GetBytes(48)))
    }
    $password = [IO.File]::ReadAllText($path).Trim()
    $salt = [Security.Cryptography.RandomNumberGenerator]::GetBytes(4)
    $hash = [Security.Cryptography.SHA256]::HashData([byte[]]($salt + [Text.Encoding]::UTF8.GetBytes($password)))
    $users += @{ name="nivaro_${service}_media"; password_hash=[Convert]::ToBase64String([byte[]]($salt + $hash)); hashing_algorithm='rabbit_password_hashing_sha256'; tags=@() }
    $vhosts += @{ name="${service}-media" }
    $permissions += @{ user="nivaro_${service}_media"; vhost="${service}-media"; configure="^${service}[.]media$"; write="^${service}[.]media$"; read="^${service}[.]media$" }
}
$definitions = @{ users=$users; vhosts=$vhosts; permissions=$permissions } | ConvertTo-Json -Depth 6
[IO.File]::WriteAllText((Join-Path $directory 'media_broker_definitions.json'), $definitions)
Write-Output 'Service-scoped media credentials prepared; existing passwords preserved. No credentials printed.'
