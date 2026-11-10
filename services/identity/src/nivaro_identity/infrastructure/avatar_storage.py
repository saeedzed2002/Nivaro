"""Local media bytes only; database ownership and activation stay in the service.

Roots must be service-owned directories, never writable by uploaders. Public is a
candidate-output root, not an authorization decision: only DB-ready references may
be served. A worker attempt gets its own immutable directory, so a stale worker
cannot overwrite another attempt or the currently active image.
"""

import os
import shutil
import tempfile
from pathlib import Path
from uuid import UUID

MAX_UPLOAD_BYTES = 8 * 1024 * 1024
MAX_OUTPUT_BYTES = 32 * 1024 * 1024


class MediaStorage:
    def __init__(self, private_root: Path, output_root: Path) -> None:
        self.private = private_root.resolve()
        self.outputs = output_root.resolve()
        if (
            self.private == self.outputs
            or self.private.is_relative_to(self.outputs)
            or self.outputs.is_relative_to(self.private)
        ):
            raise ValueError("Media roots must be disjoint")
        self.private.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.outputs.mkdir(parents=True, exist_ok=True, mode=0o750)

    @staticmethod
    def _id(value: UUID) -> str:
        if not isinstance(value, UUID):
            raise ValueError("A server-generated UUID is required")
        return value.hex

    def _source(self, job_id: UUID) -> Path:
        path = self.private / (self._id(job_id) + ".source")
        if path.is_symlink():
            raise ValueError("Media symlinks are forbidden")
        return path

    def write_original(self, job_id: UUID, content: bytes) -> None:
        if not content or len(content) > MAX_UPLOAD_BYTES:
            raise ValueError("Invalid original byte size")
        # Exclusive creation prevents retries from replacing an existing job's input.
        with self._source(job_id).open("xb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())

    def read_original(self, job_id: UUID) -> bytes:
        with self._source(job_id).open("rb") as stream:
            content = stream.read(MAX_UPLOAD_BYTES + 1)
        if not content or len(content) > MAX_UPLOAD_BYTES:
            raise ValueError("Invalid original byte size")
        return content

    def write_outputs(self, attempt_id: UUID, outputs: dict[int, bytes]) -> dict[int, str]:
        """Publish a complete attempt directory atomically on the local filesystem.

        The caller supplies only trusted decoder output; this method does not claim
        to validate pixels. Database activation occurs after this call succeeds.
        """
        key = self._id(attempt_id)
        if not outputs or outputs.keys() != {128, 256}:
            raise ValueError("Both avatar sizes are required")
        if (
            any(not data for data in outputs.values())
            or sum(map(len, outputs.values())) > MAX_OUTPUT_BYTES
        ):
            raise ValueError("Invalid output byte size")
        destination = self.outputs / key
        if destination.exists() or destination.is_symlink():
            raise FileExistsError("Attempt output already exists")
        stage = Path(tempfile.mkdtemp(prefix=".pending-", dir=self.outputs))
        try:
            for width, data in outputs.items():
                with (stage / f"{width}.webp").open("xb") as stream:
                    stream.write(data)
                    stream.flush()
                    os.fsync(stream.fileno())
            # Same-filesystem rename exposes all files together. UUID attempt names
            # are unique; a second attempt never reuses a destination identifier.
            stage.rename(destination)
        finally:
            if stage.exists():
                shutil.rmtree(stage)
        return {width: f"{key}/{width}.webp" for width in outputs}
