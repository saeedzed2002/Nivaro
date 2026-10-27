[CmdletBinding()]
param(
    [ValidateSet('Arvan', 'DockerHub')]
    [string]$Source = 'Arvan',
    [switch]$IncludeTools,
    [switch]$ListOnly
)

$ErrorActionPreference = 'Stop'
$PSNativeCommandUseErrorActionPreference = $false
$images = @(
    'node:24.22.1-bookworm-slim'
    'caddy:2.11.7'
    'python:3.13.18-slim-bookworm'
    'postgres:18.6-bookworm'
    'rabbitmq:4.4.0-management'
    'redis:8.10.3'
)
if ($IncludeTools) { $images += 'axllent/mailpit:v1.32.0' }
if ($ListOnly) { $images; return }

$engineOS = & docker info --format '{{.OSType}}'
if ($LASTEXITCODE -ne 0 -or $engineOS -ne 'linux') {
    throw 'Start Docker Desktop with the Linux container engine, then run this script again.'
}

foreach ($image in $images) {
    $installedPlatform = & docker image inspect --format '{{.Os}}/{{.Architecture}}' $image 2>$null
    if ($LASTEXITCODE -eq 0) {
        if ($installedPlatform -ne 'linux/amd64') {
            throw "Existing tag $image has platform $installedPlatform; leaving it unchanged."
        }
        Write-Host "Already available: $image"
        continue
    }

    $remote = if ($Source -eq 'Arvan') { "docker.arvancloud.ir/$image" } else { $image }
    Write-Host "Downloading $remote (linux/amd64). Ctrl+C cancels; rerun to reuse completed layers."
    & docker pull --platform linux/amd64 $remote
    if ($LASTEXITCODE -ne 0) {
        throw "Pull failed: $remote. No automatic retry. Keep the error; try -Source DockerHub if appropriate."
    }
    if ($Source -eq 'Arvan') {
        # A local alias for Compose/Dockerfile defaults; this does not download or duplicate layers.
        & docker tag $remote $image
        if ($LASTEXITCODE -ne 0) { throw "Could not create local alias: $image" }
    }
    & docker image inspect --format '{{.RepoTags}} {{.Id}}' $image
    if ($LASTEXITCODE -ne 0) { throw "Image inspection failed: $image" }
}
Write-Host 'Requested base images are available. Application packages and offline builds are separate preparation steps.'
