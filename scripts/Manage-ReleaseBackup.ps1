[CmdletBinding()]
param(
    [Parameter(Mandatory)][ValidateSet('Backup', 'Restore')][string]$Operation,
    [Parameter(Mandatory)][ValidatePattern('^[a-z0-9][a-z0-9_-]*$')][string]$Project,
    [Parameter(Mandatory)][string]$Directory
)
$ErrorActionPreference = 'Stop'
$databases = @('nivaro_catalog', 'nivaro_identity', 'nivaro_cart', 'nivaro_orders', 'nivaro_payments', 'nivaro_support')
$volumes = @('catalog_media', 'identity_media')
$mediaImage = 'python:3.13.18-slim-bookworm@sha256:93498f36dc7e24ef233bfdf6cc17d4b8bd32d94ee737143e906460d5f5a914c5'
$filenameList = @($databases | ForEach-Object { "$_.dump" }) + @($volumes | ForEach-Object { "$_.tar.gz" })
$bundlePath = $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($Directory)
$manifestPath = Join-Path $bundlePath 'manifest.json'

function Invoke-DockerCommand([string[]]$Arguments) {
    & docker @Arguments
    if ($LASTEXITCODE -ne 0) { throw "Docker $($Arguments[0]) failed (exit $LASTEXITCODE)." }
}

function Invoke-DatabaseQuery([string]$Database, [string]$Query) {
    Invoke-DockerCommand @('exec', '--user', 'postgres', $postgres, 'psql', '-XAt', '--no-password',
        '--username=postgres', "--dbname=$Database", '-v', 'ON_ERROR_STOP=1', '--command', $Query)
}

function Invoke-MediaArchive([string]$Action, [string]$Volume) {
    $volumeMode = if ($Action -eq 'restore') { 'rw' } else { 'ro' }
    $bundleMode = if ($Action -eq 'backup') { 'rw' } else { 'ro' }
    Invoke-DockerCommand @('run', '--rm', '--pull', 'never', '--network', 'none',
        '--volume', "${Project}_${Volume}:/media:$volumeMode", '--volume', "${bundlePath}:/bundle:$bundleMode",
        '--volume', ("${PSScriptRoot}/backup-media.py:/backup-media.py:ro"), $mediaImage,
        'python', '/backup-media.py', $Action, "/bundle/$Volume.tar.gz")
}

$postgresContainers = @(Invoke-DockerCommand @('ps', '-q', '--filter', "label=com.docker.compose.project=$Project",
    '--filter', 'label=com.docker.compose.service=postgres'))
$runningContainers = @(Invoke-DockerCommand @('ps', '-q', '--filter', "label=com.docker.compose.project=$Project"))
if ($postgresContainers.Count -ne 1 -or $runningContainers.Count -ne 1 -or $postgresContainers[0] -ne $runningContainers[0]) {
    throw 'Exactly one container for the project must be running, its PostgreSQL service. Stop application and worker containers first.'
}
$postgres = $postgresContainers[0]
if ((Invoke-DatabaseQuery 'postgres' "SELECT count(*) FROM pg_stat_activity WHERE backend_type = 'client backend' AND datname ~ '^nivaro_';") -ne '0') {
    throw 'PostgreSQL still has active client connections. Disconnect other clients for a consistent snapshot or restore.'
}
foreach ($volume in $volumes) {
    $labels = Invoke-DockerCommand @('volume', 'inspect', '--format', '{{json .Labels}}', "${Project}_$volume") | ConvertFrom-Json -AsHashtable
    if ($labels['com.docker.compose.project'] -ne $Project -or $labels['com.docker.compose.volume'] -ne $volume) {
        throw "The Compose-owned $volume volume for $Project is required."
    }
}

if ($Operation -eq 'Backup') {
    # Create a new directory without overwriting a previous bundle.
    if (Test-Path -LiteralPath $bundlePath) { throw 'Choose a new backup directory.' }
    New-Item -ItemType Directory -Path $bundlePath | Out-Null
} else {
    $manifest = Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json -AsHashtable
    if ($manifest.format -ne 1 -or !$manifest.project -or $manifest.project -eq $Project -or
        $manifest.files -isnot [System.Collections.IDictionary] -or $manifest.files.Count -ne $filenameList.Count) {
        throw 'Expected a complete version 1 bundle from a different Compose project.'
    }
    foreach ($filename in $filenameList) {
        $artifact = Join-Path $bundlePath $filename
        if (!$manifest.files.Contains($filename) -or
            (Get-FileHash -LiteralPath $artifact -Algorithm SHA256).Hash -ne $manifest.files[$filename]) {
            throw "Checksum mismatch for $filename. Restore has not modified the target."
        }
    }
    foreach ($database in $databases) {
        $owner = Invoke-DatabaseQuery 'postgres' "SELECT pg_get_userbyid(datdba) FROM pg_database WHERE datname = '$database';"
        if ($owner -ne $database) { throw "Initialize the $database role and database before restoring." }
        $empty = Invoke-DatabaseQuery $database @'
SELECT NOT EXISTS (
    SELECT 1 FROM pg_namespace WHERE nspname NOT IN ('public', 'information_schema') AND nspname !~ '^pg_'
    UNION ALL SELECT 1 FROM pg_class WHERE relnamespace = 'public'::regnamespace
    UNION ALL SELECT 1 FROM pg_proc WHERE pronamespace = 'public'::regnamespace
    UNION ALL SELECT 1 FROM pg_type WHERE typnamespace = 'public'::regnamespace
    UNION ALL SELECT 1 FROM pg_extension WHERE extname <> 'plpgsql'
);
'@
        if ($empty -ne 't') { throw "Restore requires an empty $database database." }
    }
    foreach ($volume in $volumes) { Invoke-MediaArchive 'check' $volume }
}

foreach ($database in $databases) {
    $filename = "$database.dump"
    $file = Join-Path $bundlePath $filename
    $stage = Invoke-DockerCommand @('exec', '--user', 'postgres', $postgres, 'mktemp', '-d', '/tmp/nivaro-backup.XXXXXXXX')
    if ($stage -cnotmatch '^/tmp/nivaro-backup\.[A-Za-z0-9]{8}$') { throw 'Unexpected temporary archive directory.' }
    $containerFile = "$stage/$filename"
    try {
        if ($Operation -eq 'Backup') {
            Invoke-DockerCommand @('exec', '--user', 'postgres', $postgres, 'pg_dump', '--no-password',
                '--username=postgres', '--format=custom', "--file=$containerFile", "--dbname=$database")
            Invoke-DockerCommand @('cp', "${postgres}:$containerFile", $file)
        } else {
            Invoke-DockerCommand @('cp', $file, "${postgres}:$containerFile")
            Invoke-DockerCommand @('exec', '--user', '0:0', $postgres, 'chown', 'postgres:postgres', $containerFile)
            Invoke-DockerCommand @('exec', '--user', 'postgres', $postgres, 'pg_restore', '--no-password',
                '--username=postgres', '--single-transaction', "--dbname=$database", $containerFile)
        }
    } finally {
        Invoke-DockerCommand @('exec', '--user', 'postgres', $postgres, 'rm', '-f', '--', $containerFile)
        Invoke-DockerCommand @('exec', '--user', 'postgres', $postgres, 'rmdir', '--', $stage)
    }
    Write-Output "${Operation}: $database"
}

foreach ($volume in $volumes) {
    Invoke-MediaArchive $Operation.ToLowerInvariant() $volume
    Write-Output "${Operation}: $volume"
}
if ($Operation -eq 'Backup') {
    $hashes = [ordered]@{}
    foreach ($filename in $filenameList) {
        $hashes[$filename] = (Get-FileHash -LiteralPath (Join-Path $bundlePath $filename) -Algorithm SHA256).Hash
    }
    [ordered]@{ format = 1; project = $Project; createdAt = [DateTimeOffset]::UtcNow.ToString('o'); files = $hashes } |
        ConvertTo-Json -Depth 3 | Set-Content -LiteralPath $manifestPath -Encoding utf8NoBOM
}
