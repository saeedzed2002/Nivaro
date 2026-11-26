[CmdletBinding()]
param(
    [string]$WebImage = 'nivaro-web:release',
    [string]$CatalogImage = 'nivaro-catalog:release',
    [string]$IdentityImage = 'nivaro-identity:release',
    [string]$CartImage = 'nivaro-cart:release',
    [string]$OrdersImage = 'nivaro-orders:release',
    [string]$PaymentsImage = 'nivaro-payments:release',
    [string]$SupportImage = 'nivaro-support:release',
    [ValidateRange(1024, 65535)][int]$Port = 8084
)
$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
$suffix = [Guid]::NewGuid().ToString('N').Substring(0, 8)
$projectPrefix = "nivaro-recovery-qa-$suffix"
$workRoot = Join-Path $root 'work'
$stage = Join-Path $workRoot $projectPrefix
$origin = "http://127.0.0.1:$Port"
$databases = @('nivaro_catalog', 'nivaro_identity', 'nivaro_cart', 'nivaro_orders', 'nivaro_payments', 'nivaro_support')
$sideNames = @('source', 'target')
$startedSides = @()

function Invoke-DockerCommand([string[]]$Arguments) {
    & docker @Arguments
    if ($LASTEXITCODE -ne 0) { throw "Docker $($Arguments[0]) failed (exit $LASTEXITCODE)." }
}

function Invoke-DrillCompose([string]$Side, [string[]]$Arguments) {
    $path = Join-Path $stage $Side
    $options = @('compose', '-p', "$projectPrefix-$Side", '--project-directory', $path)
    foreach ($file in @('compose.yaml', 'compose.media.yaml', 'compose.orders.yaml', 'compose.events.yaml',
        'compose.payments.yaml', 'compose.payment-events.yaml', 'compose.support.yaml', 'compose.recovery-qa.json')) {
        $options += @('-f', (Join-Path $path $file))
    }
    Invoke-DockerCommand ($options + $Arguments)
}

function Invoke-DrillInit([string]$Side, [string[]]$Services) {
    foreach ($service in $Services) {
        Invoke-DrillCompose $Side @('run', '--rm', '--no-deps', '--pull', 'never', $service)
    }
}

function Initialize-DrillDatabases([string]$Side) {
    Invoke-DrillCompose $Side @('up', '-d', '--no-build', '--pull', 'never', '--wait', '--wait-timeout', '60', 'postgres')
    Invoke-DrillInit $Side @('identity-db-init', 'cart-db-init', 'orders-db-init', 'payments-db-init', 'support-db-init')
}

function Get-DatabaseSnapshot([string]$Side) {
    $query = @'
SELECT format('SELECT %L, count(*), md5(coalesce(string_agg(item, '''' ORDER BY item), '''')) FROM (SELECT to_jsonb(item_row)::text AS item FROM %I.%I AS item_row) AS data;',
              tablename, schemaname, tablename)
FROM pg_tables WHERE schemaname = 'public' ORDER BY tablename \gexec
'@
    foreach ($database in $databases) {
        Write-Output $database
        $query | & docker exec -i --user postgres "$projectPrefix-$Side-postgres-1" psql -XAt -U postgres -v ON_ERROR_STOP=1 -d $database
        if ($LASTEXITCODE -ne 0) { throw "Could not read $Side database snapshot for $database." }
    }
}

function Invoke-DrillMedia([string]$Side, [string]$Action) {
    $mode = if ($Action -eq 'seed') { 'rw' } else { 'ro' }
    Invoke-DockerCommand @('run', '--rm', '--pull', 'never', '--network', 'none', '--user', '0:0',
        '--volume', "${projectPrefix}-${Side}_catalog_media:/volumes/catalog:$mode",
        '--volume', "${projectPrefix}-${Side}_identity_media:/volumes/identity:$mode",
        '--volume', "${root}/apps/web/public/images/keyboard.webp:/fixture.webp:ro",
        '--volume', "${PSScriptRoot}/backup-drill-media.py:/drill-media.py:ro",
        '--entrypoint', 'python', $CatalogImage, '/drill-media.py', $Action)
}

function Assert-Refused([string]$Message, [scriptblock]$Action) {
    try { & $Action } catch {
        if ($_.Exception.Message -like $Message) { return }
        throw
    }
    throw "Expected backup operation to refuse: $Message"
}

$services = @{
    identity = @{ environment = @{ IDENTITY_ENVIRONMENT = 'test'; IDENTITY_ALLOWED_ORIGINS = '["' + $origin + '"]' } }
    support = @{ environment = @{ SUPPORT_ALLOWED_ORIGINS = '["' + $origin + '"]' } }
}
foreach ($entry in @(
    @{ names = @('web'); image = $WebImage },
    @{ names = @('catalog', 'catalog-init', 'catalog-reservation-expiry', 'catalog-media-init', 'catalog-media-worker', 'catalog-media-dispatcher', 'catalog-event-publisher', 'catalog-delivery-consumer'); image = $CatalogImage },
    @{ names = @('identity', 'identity-init', 'identity-media-init', 'identity-media-worker', 'identity-media-dispatcher'); image = $IdentityImage },
    @{ names = @('cart', 'cart-init', 'cart-paid-consumer'); image = $CartImage },
    @{ names = @('orders', 'orders-init', 'orders-reservation-worker', 'orders-expiry-consumer', 'orders-event-publisher', 'orders-payment-consumer'); image = $OrdersImage },
    @{ names = @('payments', 'payments-init', 'payments-event-publisher', 'payments-reconciler'); image = $PaymentsImage },
    @{ names = @('support', 'support-init'); image = $SupportImage }
)) {
    foreach ($service in $entry.names) {
        if (!$services.ContainsKey($service)) { $services[$service] = @{} }
        $services[$service].image = $entry.image
    }
}

New-Item -ItemType Directory -Path $stage | Out-Null
try {
    $archive = Join-Path $stage 'tracked.tar'
    & git -C $root archive --format=tar "--output=$archive" HEAD
    if ($LASTEXITCODE -ne 0) { throw 'Could not export the tracked release configuration.' }
    foreach ($side in $sideNames) {
        $path = Join-Path $stage $side
        New-Item -ItemType Directory -Path $path | Out-Null
        & tar -xf $archive -C $path
        if ($LASTEXITCODE -ne 0) { throw 'Could not unpack the tracked release configuration.' }
        & (Join-Path $path 'scripts/Initialize-LocalSecrets.ps1')
        & (Join-Path $path 'scripts/Initialize-MediaSecrets.ps1')
        @{ services = $services } | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $path 'compose.recovery-qa.json') -Encoding utf8NoBOM
        # Change the loopback port only in the exported test project.
        $basePath = Join-Path $path 'compose.yaml'
        $base = Get-Content -LiteralPath $basePath -Raw
        $gatewayPort = "'127.0.0.1:${Port}:8080'"
        if (!$base.Contains("'127.0.0.1:8080:8080'")) { throw 'Could not identify the default release gateway binding.' }
        [IO.File]::WriteAllText($basePath, $base.Replace("'127.0.0.1:8080:8080'", $gatewayPort))
    }
    $startedSides += 'source'
    Initialize-DrillDatabases 'source'
    Invoke-DrillInit 'source' @('catalog-init', 'identity-init', 'cart-init', 'orders-init', 'payments-init', 'support-init', 'catalog-media-init', 'identity-media-init')
    Get-Content -LiteralPath (Join-Path $PSScriptRoot 'backup-drill-fixture.sql') -Raw |
        & docker exec -i --user postgres "$projectPrefix-source-postgres-1" psql -Xq -U postgres -v ON_ERROR_STOP=1 -d postgres
    if ($LASTEXITCODE -ne 0) { throw 'Could not seed the source recovery project.' }
    $sourceRows = @(Get-DatabaseSnapshot 'source')
    $sourceMedia = @(Invoke-DrillMedia 'source' 'seed')
    $bundle = Join-Path $stage 'bundle'
    & "$PSScriptRoot/Manage-ReleaseBackup.ps1" Backup "$projectPrefix-source" $bundle

    $startedSides += 'target'
    Initialize-DrillDatabases 'target'
    Invoke-DrillCompose 'target' @('create', '--no-build', 'catalog-media-init', 'identity-media-init')
    $targetProject = "$projectPrefix-target"
    $manifestPath = Join-Path $bundle 'manifest.json'
    $manifest = Get-Content -LiteralPath $manifestPath -Raw
    $invalid = $manifest | ConvertFrom-Json -AsHashtable
    $invalid.files['nivaro_support.dump'] = '0' * 64
    try {
        $invalid | ConvertTo-Json -Depth 3 | Set-Content -LiteralPath $manifestPath -Encoding utf8NoBOM
        Assert-Refused 'Checksum mismatch for nivaro_support.dump*' {
            & "$PSScriptRoot/Manage-ReleaseBackup.ps1" Restore $targetProject $bundle
        }
    } finally { [IO.File]::WriteAllText($manifestPath, $manifest) }
    & "$PSScriptRoot/Manage-ReleaseBackup.ps1" Restore $targetProject $bundle
    if (Compare-Object $sourceRows @(Get-DatabaseSnapshot 'target') -SyncWindow 0) { throw 'Restored table contents differ from the source.' }
    if (Compare-Object $sourceMedia @(Invoke-DrillMedia 'target' 'verify') -SyncWindow 0) { throw 'Restored media bytes or ownership differ from the source.' }
    Assert-Refused 'Restore requires an empty nivaro_catalog database.' {
        & "$PSScriptRoot/Manage-ReleaseBackup.ps1" Restore $targetProject $bundle
    }

    Invoke-DrillCompose 'target' @('up', '-d', '--no-build', '--pull', 'never', '--wait', '--wait-timeout', '120')
    $headers = @{ Origin = $origin }
    $phone = '+12025550100'
    $challenge = Invoke-RestMethod "$origin/api/v1/auth/otp/request" -Method Post -Headers $headers -ContentType 'application/json' -Body (@{ phone = $phone } | ConvertTo-Json)
    Invoke-RestMethod "$origin/api/v1/auth/otp/verify" -Method Post -Headers $headers -ContentType 'application/json' -SessionVariable session `
        -Body (@{ phone = $phone; challenge_id = $challenge.challenge_id; code = $challenge.development_code } | ConvertTo-Json) | Out-Null
    $historyPath = '/api/v1/support/conversations/baca0000-0000-4000-8000-000000000050/messages'
    $history = Invoke-RestMethod "$origin$historyPath" -WebSession $session
    if ($history.messages.Count -ne 1 -or $history.messages[0].body -ne 'پیام آزمایشی بازیابی') { throw 'The restored message is missing from the customer history.' }
    $order = Invoke-RestMethod "$origin/api/v1/orders/baca0000-0000-4000-8000-000000000030" -WebSession $session
    if ($order.status -ne 'paid' -or $order.totals.currency -ne 'USD' -or $order.totals.total_minor -ne 4700) { throw 'The restored order status or total differs.' }
    $avatarPath = '/api/v1/me/avatar/baca0000-0000-4000-8000-000000000003/128'
    foreach ($path in @($historyPath, $avatarPath)) {
        $anonymous = Invoke-WebRequest "$origin$path" -SkipHttpErrorCheck
        if ($anonymous.StatusCode -ne 401) { throw "Restored private resource returned HTTP $($anonymous.StatusCode) without authentication." }
    }
    $catalogDownload = Join-Path $stage 'catalog.webp'
    $avatarDownload = Join-Path $stage 'avatar.webp'
    Invoke-WebRequest "$origin/api/v1/catalog/images/baca0000-0000-4000-8000-000000000011/320" -OutFile $catalogDownload
    Invoke-WebRequest "$origin$avatarPath" -WebSession $session -OutFile $avatarDownload
    $catalogHash = (($sourceMedia | Where-Object { $_ -like 'catalog:outputs/*' }) -split ':')[-1]
    $avatarHash = (($sourceMedia | Where-Object { $_ -like 'identity:outputs/*' }) -split ':')[-1]
    if ((Get-FileHash $catalogDownload).Hash -ne $catalogHash -or (Get-FileHash $avatarDownload).Hash -ne $avatarHash) {
        throw 'Media served after restore differs from the backed-up output.'
    }
    Write-Output 'Restore drill passed: six databases, both media volumes, corruption and overwrite refusal, authenticated order and support reads, public image and private avatar.'
} finally {
    $cleanupFailed = $false
    foreach ($side in $startedSides) {
        try { Invoke-DrillCompose $side @('down', '--volumes') } catch { $cleanupFailed = $true; Write-Warning $_ }
    }
    $resolvedWork = (Resolve-Path -LiteralPath $workRoot).Path
    $resolvedStage = Get-Item -LiteralPath $stage -Force
    if ($cleanupFailed -or $resolvedStage.FullName -ne (Join-Path $resolvedWork $projectPrefix) -or
        $resolvedStage.Attributes.HasFlag([IO.FileAttributes]::ReparsePoint) -or $projectPrefix -cnotmatch '^nivaro-recovery-qa-[0-9a-f]{8}$') {
        throw 'Recovery workspace was retained because cleanup could not be confirmed.'
    }
    Remove-Item -LiteralPath $resolvedStage.FullName -Recurse -Force
}
