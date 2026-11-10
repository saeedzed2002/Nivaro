"""Retention for service-owned media only; active and in-flight files are retained."""

import asyncio
import re
import shutil
import time
from pathlib import Path

from sqlalchemy import select

from nivaro_identity.infrastructure.database import Database
from nivaro_identity.infrastructure.models import AvatarJob, AvatarSlot
from nivaro_identity.settings import Settings

RETENTION_SECONDS = 7 * 24 * 60 * 60


def clean_root(root: Path, keep: set[str], *, originals: bool, cutoff: float) -> int:
    root = root.resolve()
    if not root.is_dir():
        return 0
    count = 0
    for entry in root.iterdir():
        # Never follow symlinks or act on unrecognized names in this directory.
        valid = (
            re.fullmatch(r"[a-f0-9]{32}\.source", entry.name)
            if originals
            else re.fullmatch(r"[a-f0-9]{32}|\.pending-[a-zA-Z0-9_-]+", entry.name)
        )
        if not valid or entry.is_symlink() or entry.name in keep:
            continue
        try:
            if entry.stat().st_mtime >= cutoff:
                continue
            if originals and entry.is_file():
                entry.unlink()
                count += 1
            elif not originals and entry.is_dir():
                shutil.rmtree(entry)
                count += 1
        except FileNotFoundError:
            pass  # Another recovery pass already removed it.
    return count


async def cleanup(database: Database, settings: Settings) -> int:
    async with database.sessions() as db:
        pending = list(
            await db.scalars(
                select(AvatarJob).where(AvatarJob.state.in_(["uploaded", "processing"]))
            )
        )
        active = list(
            await db.scalars(
                select(AvatarJob).join(AvatarSlot, AvatarSlot.active_job_id == AvatarJob.id)
            )
        )
        originals = {f"{job.id.hex}.source" for job in pending}
        attempts = {job.attempt_id.hex for job in pending if job.attempt_id}
        attempts.update(job.attempt_id.hex for job in active if job.attempt_id)
    # The retention interval exceeds every worker lease/task limit. A fresh
    # replacement cannot be aged out between the DB snapshot and this deletion.
    cutoff = time.time() - RETENTION_SECONDS
    private = await asyncio.to_thread(
        clean_root, settings.media_private_root, originals, originals=True, cutoff=cutoff
    )
    outputs = await asyncio.to_thread(
        clean_root, settings.media_output_root, attempts, originals=False, cutoff=cutoff
    )
    return private + outputs
