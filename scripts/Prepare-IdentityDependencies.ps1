# Uses the existing Python image; one bounded attempt, no base-image pulls.
param(
    [uri]$IndexUrl = 'https://pypi.org/simple'
)

$ErrorActionPreference = 'Stop'
if (-not $IndexUrl.IsAbsoluteUri -or $IndexUrl.Scheme -ne 'https' -or
    $IndexUrl.UserInfo -or $IndexUrl.Query -or $IndexUrl.Fragment) {
    throw 'Use an absolute HTTPS package index URL without embedded credentials, query or fragment.'
}
$root = Split-Path $PSScriptRoot -Parent
$source = Join-Path $root 'services/identity'
$cache = Join-Path $root 'work/python-cache'
New-Item -ItemType Directory -Path $cache -Force | Out-Null
$install = @'
set -eu
wheel=/seed/uv-0.13.5-py3-none-manylinux_2_17_x86_64.manylinux2014_x86_64.whl
if [ -f "$wheel" ]; then
  pip install --disable-pip-version-check --no-index --no-deps "$wheel"
else
  pip install --disable-pip-version-check --timeout 20 --retries 0 uv==0.13.5
fi
if [ ! -f uv.lock ]; then uv lock; fi
uv sync --frozen --no-editable
'@
docker run --rm --pull never `
    -e UV_PROJECT_ENVIRONMENT=/app/.venv -v "${root}/packages:/workspace/packages:ro" -v "${source}:/workspace/services/identity" -v "${source}:/app" -v "${cache}:/seed:ro" `
    -v 'nivaro-python-download-cache:/root/.cache' `
    -e "UV_DEFAULT_INDEX=$($IndexUrl.AbsoluteUri)" -e "PIP_INDEX_URL=$($IndexUrl.AbsoluteUri)" `
    -e UV_HTTP_TIMEOUT=20 -e UV_HTTP_RETRIES=0 -e UV_LINK_MODE=copy `
    -w /workspace/services/identity python:3.13.18-slim-bookworm sh -c $install
if ($LASTEXITCODE -ne 0) {
    throw 'Identity dependencies remain incomplete. Do not run Verify-IdentityFoundation.ps1 yet. Restore package connectivity or use the documented HTTPS mirror via -IndexUrl; do not change TLS or dependency pins. Existing lockfiles keep their recorded download URLs.'
}
Write-Output 'Identity lockfile and frozen Linux environment prepared. This does not verify the service or complete P03.'
