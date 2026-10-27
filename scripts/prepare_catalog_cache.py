"""Run in pinned Linux Python with the existing download volume mounted read-only."""
import shutil
import tarfile
import zipfile
from pathlib import Path

destination = Path('/output')
wheel = destination / 'uv-0.13.5-py3-none-manylinux_2_17_x86_64.manylinux2014_x86_64.whl'
for cached in Path('/cache/pip').rglob('*.body'):
    if cached.stat().st_size < 10_000_000 or not zipfile.is_zipfile(cached):
        continue
    with zipfile.ZipFile(cached) as archive:
        if 'uv-0.13.5.dist-info/METADATA' in archive.namelist():
            shutil.copyfile(cached, wheel)
            break
else:
    raise SystemExit('Pinned uv wheel is absent from the existing download cache.')
with tarfile.open(destination / 'uv-cache.tar.gz', 'w:gz', dereference=False) as archive:
    archive.add('/cache/uv', arcname='uv')
print('Prepared pinned uv wheel and Linux cache archive. No network used.')
