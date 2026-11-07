from uuid import uuid4

import pytest

from nivaro_catalog.infrastructure.media_storage import MAX_UPLOAD_BYTES, MediaStorage


def test_private_original_is_bounded_and_cannot_be_replaced(tmp_path):
    store = MediaStorage(tmp_path / "private", tmp_path / "outputs")
    job = uuid4()
    store.write_original(job, b"private input")
    assert store.read_original(job) == b"private input"
    assert list(store.outputs.iterdir()) == []
    with pytest.raises(FileExistsError):
        store.write_original(job, b"replacement")
    for invalid in (b"", b"x" * (MAX_UPLOAD_BYTES + 1)):
        with pytest.raises(ValueError):
            store.write_original(uuid4(), invalid)
    with pytest.raises(ValueError):
        store.write_original("../escape", b"x")
    assert store.read_original(job) == b"private input"


def test_outputs_are_immutable_and_failed_attempt_preserves_previous(tmp_path, monkeypatch):
    store = MediaStorage(tmp_path / "private", tmp_path / "outputs")
    attempt = uuid4()
    paths = store.write_outputs(attempt, {320: b"small", 640: b"large"})
    with pytest.raises(FileExistsError):
        store.write_outputs(attempt, {320: b"changed"})
    from pathlib import Path

    def fail_rename(*args):
        raise OSError("simulated filesystem failure")

    monkeypatch.setattr(Path, "rename", fail_rename)
    with pytest.raises(OSError):
        store.write_outputs(uuid4(), {320: b"new"})
    assert (store.outputs / paths[320]).read_bytes() == b"small"
    assert (store.outputs / paths[640]).read_bytes() == b"large"
    assert len(list(store.outputs.iterdir())) == 1


def test_storage_rejects_overlapping_roots_and_unsafe_source_links(tmp_path):
    with pytest.raises(ValueError):
        MediaStorage(tmp_path, tmp_path / "public")
    store = MediaStorage(tmp_path / "private", tmp_path / "outputs")
    external = tmp_path / "unrelated"
    external.write_bytes(b"must not read")
    job = uuid4()
    (store.private / f"{job.hex}.source").symlink_to(external)
    with pytest.raises(ValueError):
        store.read_original(job)
    with pytest.raises(ValueError):
        store.write_outputs(uuid4(), {256: b"invalid product size"})
