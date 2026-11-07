$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
$project = 'nivaro-p04-media-qa-' + [Guid]::NewGuid().ToString('N').Substring(0,8)
$compose = @('compose','-p',$project,'-f',"$root/compose.yaml",'-f',"$root/compose.identity-qa.yaml",'-f',"$root/compose.media.yaml",'-f',"$root/compose.media-qa.yaml")
try {
    docker @compose up -d --no-build --pull never --wait --wait-timeout 120
    if ($LASTEXITCODE -ne 0) { throw 'Disposable media stack failed readiness.' }
    docker @compose cp "$root/scripts/verify_catalog_media.py" catalog-media-worker:/tmp/verify_media.py
    if ($LASTEXITCODE -ne 0) { throw 'Could not copy media probe.' }
    docker @compose exec -T -e NIVARO_MEDIA_QA=disposable catalog-media-worker python /tmp/verify_media.py normal
    if ($LASTEXITCODE -ne 0) { throw 'Real queue processing failed.' }
    $job = docker @compose exec -T -e NIVARO_MEDIA_QA=disposable catalog-media-worker python /tmp/verify_media.py large
    if ($LASTEXITCODE -ne 0 -or $job -notmatch '^[0-9a-f-]{36}$') { throw 'Worker-loss probe did not observe a processing claim.' }
    docker @compose kill -s SIGKILL catalog-media-worker
    if ($LASTEXITCODE -ne 0) { throw 'Worker-loss injection failed.' }
    docker @compose up -d --no-deps --no-build --pull never catalog-media-worker
    if ($LASTEXITCODE -ne 0) { throw 'Worker restart failed.' }
    docker @compose exec -T -e NIVARO_MEDIA_QA=disposable catalog-media-worker python /tmp/verify_media.py recovered $job
    if ($LASTEXITCODE -ne 0) { throw 'Worker-loss recovery failed.' }
} catch {
    docker @compose logs --tail 30 catalog-media-worker catalog-media-dispatcher rabbitmq
    throw
} finally {
    # Only the uniquely named, freshly created QA project's stores are disposable.
    if ($project -notmatch '^nivaro-p04-media-qa-[a-f0-9]{8}$') { throw 'Unsafe cleanup target.' }
    docker @compose down --volumes
}
