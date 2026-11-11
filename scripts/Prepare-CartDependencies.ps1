param([switch]$Offline)
$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
$network = if ($Offline) { @('--network','none') } else { @() }
$install = @'
set -eu
pip install --no-index --no-deps /seed/uv-0.13.5-py3-none-manylinux_2_17_x86_64.manylinux2014_x86_64.whl
uv sync --frozen --no-editable
uv pip check --python .venv/bin/python
'@
docker run --rm --pull never @network -v "${root}/services/cart:/app" `
    -v "${root}/work/python-cache:/seed:ro" -v nivaro-python-download-cache:/root/.cache `
    -e "UV_OFFLINE=$($Offline.IsPresent.ToString().ToLowerInvariant())" `
    -e UV_HTTP_TIMEOUT=20 -e UV_HTTP_RETRIES=0 -e UV_LINK_MODE=copy -w /app `
    python:3.13.18-slim-bookworm sh -ec $install
if ($LASTEXITCODE -ne 0) { throw 'Cart dependency preparation failed; inspect connectivity or cache before retrying.' }
