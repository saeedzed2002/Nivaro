param([switch]$WithLoad)

$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
$project = 'nivaro-p04-cache-qa-' + [Guid]::NewGuid().ToString('N').Substring(0,8)
$compose = @('compose','-p',$project,'-f',"$root/compose.yaml",'-f',"$root/compose.identity-qa.yaml",'-f',"$root/compose.media.yaml",'-f',"$root/compose.media-qa.yaml")
try {
    $services = if ($WithLoad) { @('catalog', 'redis-cache') } else { @() }
    docker @compose up -d --no-build --pull never --wait --wait-timeout 120 @services
    if ($LASTEXITCODE -ne 0) { throw 'Disposable cache stack failed readiness.' }
    docker @compose cp "$root/scripts/verify_catalog_cache.py" catalog:/tmp/verify_cache.py
    if ($LASTEXITCODE -ne 0) { throw 'Could not copy cache checks.' }
    docker @compose exec -T -e NIVARO_CACHE_QA=disposable catalog python /tmp/verify_cache.py normal
    if ($LASTEXITCODE -ne 0) { throw 'Cache concurrency checks failed.' }
    if ($WithLoad) {
        if ($project -notmatch '^nivaro-p04-cache-qa-[a-f0-9]{8}$') { throw 'Unsafe load fixture target.' }
        Get-Content "$root/scripts/catalog-load-fixture.sql" -Raw | docker @compose exec -T postgres psql -X -v ON_ERROR_STOP=1 -U postgres -d nivaro_catalog
        if ($LASTEXITCODE -ne 0) { throw 'Disposable catalog load fixture failed.' }
        docker @compose cp "$root/scripts/verify_catalog_load.py" catalog:/tmp/verify_load.py
        if ($LASTEXITCODE -ne 0) { throw 'Could not copy the catalog load verifier.' }
        $warmLoad = docker @compose exec -T -e NIVARO_CACHE_QA=disposable catalog python /tmp/verify_load.py warm
        if ($LASTEXITCODE -ne 0) { throw 'Warm catalog load checks failed.' }
        Write-Output $warmLoad
    }
    docker @compose stop redis-cache
    if ($LASTEXITCODE -ne 0) { throw 'Cache outage injection failed.' }
    docker @compose exec -T -e NIVARO_CACHE_QA=disposable catalog python /tmp/verify_cache.py outage
    if ($LASTEXITCODE -ne 0) { throw 'Cache outage checks failed.' }
    if ($WithLoad) {
        $outageLoad = docker @compose exec -T -e NIVARO_CACHE_QA=disposable catalog python /tmp/verify_load.py outage
        if ($LASTEXITCODE -ne 0) { throw 'Catalog load checks during cache outage failed.' }
        Write-Output $outageLoad
        if (($warmLoad | ConvertFrom-Json).payload_sha256 -ne ($outageLoad | ConvertFrom-Json).payload_sha256) {
            throw 'Catalog results changed after cache interruption.'
        }
    }
    docker @compose start redis-cache
    if ($LASTEXITCODE -ne 0) { throw 'Cache restart failed.' }
    Start-Sleep -Seconds 3
    docker @compose exec -T -e NIVARO_CACHE_QA=disposable catalog python /tmp/verify_cache.py restored
    if ($LASTEXITCODE -ne 0) { throw 'Cache recovery checks failed.' }
} finally {
    if ($project -notmatch '^nivaro-p04-cache-qa-[a-f0-9]{8}$') { throw 'Unsafe cleanup target.' }
    docker @compose down --volumes
}
