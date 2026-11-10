"""Recover and dispatch avatar jobs; publish outside all database transactions."""

import asyncio
import logging

from sqlalchemy import text

from nivaro_identity.infrastructure.avatar_cleanup import cleanup
from nivaro_identity.infrastructure.avatars import claim_dispatch, confirm_dispatch, recover_jobs
from nivaro_identity.infrastructure.database import Database
from nivaro_identity.media_worker import app
from nivaro_identity.settings import Settings


async def run() -> None:
    database = Database(Settings())
    next_cleanup = 0.0
    try:
        while True:
            try:
                if asyncio.get_running_loop().time() >= next_cleanup:
                    # A separate schedule lock keeps only one retention pass active.
                    async with database.sessions() as db, db.begin():
                        if await db.scalar(text("SELECT pg_try_advisory_xact_lock(71405, 3)")):
                            await cleanup(database, Settings())
                    next_cleanup = asyncio.get_running_loop().time() + 3600
                async with database.sessions() as db, db.begin():
                    if await db.scalar(text("SELECT pg_try_advisory_xact_lock(71405, 2)")):
                        await recover_jobs(db)
                async with database.sessions() as db, db.begin():
                    claim = await claim_dispatch(db)
                if claim:
                    job_id, claim_id = claim
                    # A crash after broker confirmation but before this DB update
                    # causes repeat delivery with the same ID; claims make it safe.
                    await asyncio.to_thread(
                        app.send_task,
                        "identity.process_avatar",
                        args=[str(job_id), 1],
                        task_id=str(job_id),
                        queue="identity.media",
                        timeout=5,
                        confirm_timeout=5,
                    )
                    async with database.sessions() as db, db.begin():
                        await confirm_dispatch(db, job_id, claim_id)
            except Exception:
                # Credentials, raw uploads and SQL never enter error logs.
                logging.getLogger(__name__).warning("identity_media_dispatch_retry")
            await asyncio.sleep(2)
    finally:
        await database.engine.dispose()


if __name__ == "__main__":
    asyncio.run(run())
