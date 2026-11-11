$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
$project = 'nivaro-p04-cache-qa-' + [Guid]::NewGuid().ToString('N').Substring(0,8)
$compose = @('compose','-p',$project,'-f',"$root/compose.yaml",'-f',"$root/compose.identity-qa.yaml",'-f',"$root/compose.media.yaml",'-f',"$root/compose.media-qa.yaml")
try {
    docker @compose up -d --no-build --pull never --wait --wait-timeout 120
    if ($LASTEXITCODE -ne 0) { throw 'Disposable cache stack failed readiness.' }
    docker @compose cp "$root/scripts/verify_catalog_cache.py" catalog:/tmp/verify_cache.py
    if ($LASTEXITCODE -ne 0) { throw 'Could not copy cache checks.' }
    docker @compose exec -T -e NIVARO_CACHE_QA=disposable catalog python /tmp/verify_cache.py normal
    if ($LASTEXITCODE -ne 0) { throw 'Cache concurrency checks failed.' }
    docker @compose stop redis-cache
    if ($LASTEXITCODE -ne 0) { throw 'Cache outage injection failed.' }
    docker @compose exec -T -e NIVARO_CACHE_QA=disposable catalog python /tmp/verify_cache.py outage
    if ($LASTEXITCODE -ne 0) { throw 'Cache outage checks failed.' }
    docker @compose start redis-cache
    if ($LASTEXITCODE -ne 0) { throw 'Cache restart failed.' }
    Start-Sleep -Seconds 3
    docker @compose exec -T -e NIVARO_CACHE_QA=disposable catalog python /tmp/verify_cache.py restored
    if ($LASTEXITCODE -ne 0) { throw 'Cache recovery checks failed.' }
} finally {
    if ($project -notmatch '^nivaro-p04-cache-qa-[a-f0-9]{8}$') { throw 'Unsafe cleanup target.' }
    docker @compose down --volumes
}
