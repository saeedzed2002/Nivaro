$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path $PSScriptRoot -Parent
$cachePath = Join-Path $projectRoot 'work/python-cache'
New-Item -ItemType Directory -Force -Path $cachePath | Out-Null
Set-Content -LiteralPath (Join-Path $cachePath '.dockerignore') -Value 'uv-cache/'
docker run --rm --pull never --network none `
  -v 'nivaro-python-download-cache:/cache:ro' `
  -v "${cachePath}:/output" `
  -v "${PSScriptRoot}/prepare_catalog_cache.py:/prepare.py:ro" `
  python:3.13.18-slim-bookworm@sha256:93498f36dc7e24ef233bfdf6cc17d4b8bd32d94ee737143e906460d5f5a914c5 `
  python /prepare.py
if ($LASTEXITCODE -ne 0) { throw 'Existing Python cache could not be exported.' }
