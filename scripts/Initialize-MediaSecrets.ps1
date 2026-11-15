$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
$directory = Join-Path $root 'work/secrets'
New-Item -ItemType Directory -Path $directory -Force | Out-Null
$users = @()
$permissions = @()
$vhosts = @()
function New-BrokerUser($name, $fileName) {
    $path = Join-Path $directory $fileName
    if (-not (Test-Path -LiteralPath $path)) {
        [IO.File]::WriteAllText($path, [Convert]::ToBase64String([Security.Cryptography.RandomNumberGenerator]::GetBytes(48)))
    }
    $password = [IO.File]::ReadAllText($path).Trim()
    $salt = [Security.Cryptography.RandomNumberGenerator]::GetBytes(4)
    $hash = [Security.Cryptography.SHA256]::HashData([byte[]]($salt + [Text.Encoding]::UTF8.GetBytes($password)))
    return @{ name=$name; password_hash=[Convert]::ToBase64String([byte[]]($salt + $hash)); hashing_algorithm='rabbit_password_hashing_sha256'; tags=@() }
}
foreach ($service in @('catalog', 'identity')) {
    $users += New-BrokerUser "nivaro_${service}_media" "${service}_media_broker_password.txt"
    $vhosts += @{ name="${service}-media" }
    $permissions += @{ user="nivaro_${service}_media"; vhost="${service}-media"; configure="^${service}[.]media$"; write="^${service}[.]media$"; read="^${service}[.]media$" }
}
$eventHost = 'commerce-events'
$expiryQueue = 'orders.inventory.reservation.expired.v1'
$errorQueue = "$expiryQueue.error"
$users += New-BrokerUser 'nivaro_catalog_events' 'catalog_event_broker_password.txt'
$users += New-BrokerUser 'nivaro_orders_events' 'orders_event_broker_password.txt'
$vhosts += @{ name=$eventHost }
$permissions += @(
    @{ user='nivaro_catalog_events'; vhost=$eventHost; configure='^$'; write='^nivaro[.]events$'; read='^$' }
    @{ user='nivaro_orders_events'; vhost=$eventHost; configure='^$'; write='^$'; read='^orders[.]inventory[.]reservation[.]expired[.]v1$' }
)
$definitions = @{
    users=$users; vhosts=$vhosts; permissions=$permissions
    exchanges=@(
        @{ name='nivaro.events'; vhost=$eventHost; type='topic'; durable=$true; auto_delete=$false; internal=$false; arguments=@{} }
        @{ name='nivaro.events.errors'; vhost=$eventHost; type='direct'; durable=$true; auto_delete=$false; internal=$false; arguments=@{} }
    )
    queues=@(
        @{ name=$expiryQueue; vhost=$eventHost; durable=$true; auto_delete=$false; arguments=@{'x-queue-type'='quorum'} }
        @{ name=$errorQueue; vhost=$eventHost; durable=$true; auto_delete=$false; arguments=@{'x-queue-type'='quorum'} }
    )
    bindings=@(
        @{ source='nivaro.events'; vhost=$eventHost; destination=$expiryQueue; destination_type='queue'; routing_key='inventory.reservation.expired'; arguments=@{} }
        @{ source='nivaro.events.errors'; vhost=$eventHost; destination=$errorQueue; destination_type='queue'; routing_key=$errorQueue; arguments=@{} }
    )
    policies=@(
        @{ name='orders-expiry-delivery'; vhost=$eventHost; pattern='^orders[.]inventory[.]reservation[.]expired[.]v1$'; 'apply-to'='quorum_queues'; priority=0
           definition=@{'delivery-limit'=5; 'dead-letter-exchange'='nivaro.events.errors'; 'dead-letter-routing-key'=$errorQueue; 'dead-letter-strategy'='at-least-once'; overflow='reject-publish'} }
    )
} | ConvertTo-Json -Depth 8
[IO.File]::WriteAllText((Join-Path $directory 'media_broker_definitions.json'), $definitions)
Write-Output 'Service-scoped media and event broker credentials prepared. Existing passwords were preserved.'
