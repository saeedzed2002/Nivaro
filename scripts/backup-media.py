"""Archive and restore stopped Nivaro media volumes inside a Docker helper."""

import argparse
import tarfile
from pathlib import Path, PurePosixPath


def regular_member(member: tarfile.TarInfo) -> tarfile.TarInfo:
    path = PurePosixPath(member.name)
    if path.is_absolute() or ".." in path.parts or not (member.isdir() or member.isfile()):
        raise ValueError(f"Unsupported media archive entry: {member.name!r}")
    return member


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("backup", "check", "restore"))
    parser.add_argument("archive", type=Path)
    args = parser.parse_args()
    media = Path("/media")
    if args.operation == "backup":
        with tarfile.open(args.archive, "x:gz", dereference=False) as archive:
            archive.add(media, arcname=".", filter=regular_member)
        return

    if any(media.iterdir()):
        raise ValueError("Restore media volume must be empty")
    with tarfile.open(args.archive, "r:gz") as archive:
        members = archive.getmembers()
        names = {PurePosixPath(regular_member(member).name) for member in members}
        if not members or len(members) != len(names) or PurePosixPath(".") not in names:
            raise ValueError("Expected a complete archive with unique media paths")
        if args.operation == "restore":
            archive.extractall(media, members=members, numeric_owner=True, filter="tar")


if __name__ == "__main__":
    main()
