import os
import time
from uuid import uuid4

from nivaro_catalog.application.media_cleanup import clean_root


def test_retention_keeps_live_recent_unknown_and_symlink_targets(tmp_path):
    active, stale, recent = [f"{uuid4().hex}.source" for _ in range(3)]
    for name in (active, stale, recent, "unrelated.txt"):
        (tmp_path / name).write_bytes(b"data")
    old = time.time() - 1000
    for name in (active, stale, "unrelated.txt"):
        os.utime(tmp_path / name, (old, old))
    link = tmp_path / f"{uuid4().hex}.source"
    link.symlink_to(tmp_path / "unrelated.txt")
    assert clean_root(tmp_path, {active}, originals=True, cutoff=time.time() - 100) == 1
    assert not (tmp_path / stale).exists()
    assert all((tmp_path / name).exists() for name in (active, recent, "unrelated.txt"))
    assert link.is_symlink()
    assert clean_root(tmp_path, {active}, originals=True, cutoff=time.time() - 100) == 0
