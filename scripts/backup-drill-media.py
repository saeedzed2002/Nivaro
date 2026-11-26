"""Create or fingerprint the synthetic media used by the release restore drill."""

import sys
from hashlib import file_digest
from pathlib import Path
from shutil import copyfile
from stat import S_IMODE

from PIL import Image, ImageOps

MEDIA = (
    ("catalog", 10001, "baca0000000040008000000000000011", "baca0000000040008000000000000012", 320),
    (
        "identity",
        10002,
        "baca0000000040008000000000000003",
        "baca0000000040008000000000000004",
        128,
    ),
)


def main() -> None:
    for name, owner, job, attempt, size in MEDIA:
        root = Path("/volumes") / name
        original = root / "private" / f"{job}.source"
        output = root / "outputs" / attempt / f"{size}.webp"
        if sys.argv[1] == "seed":
            from os import chown

            output.parent.mkdir(mode=0o750)
            copyfile("/fixture.webp", original)
            with Image.open("/fixture.webp") as image:
                ImageOps.fit(image.convert("RGB"), (size, size)).save(output, format="WEBP")
            chown(output.parent, owner, owner)
            for path, mode in ((original, 0o600), (output, 0o640)):
                chown(path, owner, owner)
                path.chmod(mode)
        for path in (original, output):
            info = path.stat()
            with path.open("rb") as contents:
                digest = file_digest(contents, "sha256").hexdigest()
            print(
                f"{name}:{path.relative_to(root)}:{info.st_uid}:{info.st_gid}:{S_IMODE(info.st_mode):o}:{digest}"
            )


if __name__ == "__main__":
    main()
