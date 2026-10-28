"""Dependency smoke check; not a test of the future worker/application implementation."""

import hashlib
import io
import json
from importlib import import_module
from importlib.metadata import version
from pathlib import Path

from PIL import Image, features

for module in ("celery", "cryptography", "jwt", "kombu", "python_multipart", "redis"):
    import_module(module)
assert features.check("webp"), "Selected Pillow wheel lacks WebP encoding."
buffer = io.BytesIO()
Image.new("RGB", (2, 2), (20, 80, 200)).save(buffer, format="WEBP")
buffer.seek(0)
with Image.open(buffer) as decoded:
    decoded.load()
    assert decoded.size == (2, 2) and decoded.format == "WEBP"

versions = {name: version(name) for name in ("celery", "Pillow", "python-multipart", "kombu")}
lock = Path("/preparation/uv.lock")
Path("/preparation/ready.json").write_text(
    json.dumps(
        {
            "lock_sha256": hashlib.sha256(lock.read_bytes()).hexdigest(),
            "versions": versions,
            "webp_roundtrip": True,
        },
        indent=2,
    )
    + "\n"
)
print(json.dumps(versions))
print(
    "P04_DEPENDENCIES_READY: imports and WebP roundtrip passed. No broker/worker feature is verified."
)
