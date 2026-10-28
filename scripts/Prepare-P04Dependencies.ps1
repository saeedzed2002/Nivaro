# Download only Python dependencies into an isolated Linux probe and existing cache.
param(
    [uri]$IndexUrl = 'https://pypi.org/simple',
    [switch]$Offline
)

$ErrorActionPreference = 'Stop'
if (-not $IndexUrl.IsAbsoluteUri -or $IndexUrl.Scheme -ne 'https' -or
    $IndexUrl.UserInfo -or $IndexUrl.Query -or $IndexUrl.Fragment) {
    throw 'Use an absolute HTTPS package index without credentials, query or fragment.'
}
$projectRoot = Split-Path $PSScriptRoot -Parent
$preparation = Join-Path $projectRoot 'work/p04-dependencies'
$seed = Join-Path $projectRoot 'work/python-cache'
$pythonImage = 'python:3.13.18-slim-bookworm@sha256:93498f36dc7e24ef233bfdf6cc17d4b8bd32d94ee737143e906460d5f5a914c5'
docker image inspect $pythonImage --format '{{.Os}}/{{.Architecture}}'
if ($LASTEXITCODE -ne 0) { throw 'The selected Python base image must already be present; this helper never pulls images.' }
New-Item -ItemType Directory -Path $preparation -Force | Out-Null
New-Item -ItemType Directory -Path $seed -Force | Out-Null
$networkArgs = @()
if ($Offline) { $networkArgs = @('--network', 'none') }
$install = @'
set -eu
wheel=/seed/uv-0.13.5-py3-none-manylinux_2_17_x86_64.manylinux2014_x86_64.whl
if [ -f "$wheel" ]; then
  pip install --disable-pip-version-check --no-index --no-deps "$wheel"
else
  if [ "$UV_OFFLINE" = true ]; then echo 'Pinned uv seed wheel is missing.'; exit 1; fi
  pip install --disable-pip-version-check --timeout 20 --retries 0 uv==0.13.5
fi
python /repo/scripts/prepare_p04_dependencies.py
uv lock --no-build
uv sync --frozen --no-build
uv pip check --python .venv/bin/python
.venv/bin/python /repo/scripts/verify_p04_dependencies.py
'@
docker run --rm --pull never @networkArgs `
    -v "${projectRoot}:/repo:ro" -v "${preparation}:/preparation" -v "${seed}:/seed:ro" `
    -v 'nivaro-python-download-cache:/root/.cache' `
    -e "UV_DEFAULT_INDEX=$($IndexUrl.AbsoluteUri)" -e "PIP_INDEX_URL=$($IndexUrl.AbsoluteUri)" `
    -e "UV_OFFLINE=$($Offline.IsPresent.ToString().ToLowerInvariant())" `
    -e UV_HTTP_TIMEOUT=20 -e UV_HTTP_RETRIES=0 -e UV_LINK_MODE=copy `
    -w /preparation $pythonImage sh -c $install
if ($LASTEXITCODE -ne 0) {
    throw 'P04 preparation is incomplete. Existing services are unchanged. Retry once connectivity is available or use the documented HTTPS mirror; do not change TLS or package pins.'
}
Write-Output 'P04 dependencies prepared. Run again with -Offline to verify the cached Linux environment without network.'
