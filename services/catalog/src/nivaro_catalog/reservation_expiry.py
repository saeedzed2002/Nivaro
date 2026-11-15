"""Scan held reservations with bounded transactions using the database deadline."""

import asyncio
import logging

from sqlalchemy.exc import SQLAlchemyError

from nivaro_catalog.application.checkout import expire_one
from nivaro_catalog.infrastructure.database import Database
from nivaro_catalog.settings import Settings

log = logging.getLogger(__name__)


async def run() -> None:
    database = Database(Settings())
    try:
        async with database.sessions() as db:
            while True:
                try:
                    for _ in range(32):
                        if not await expire_one(db):
                            break
                    else:
                        await asyncio.sleep(0.1)
                        continue
                except SQLAlchemyError:
                    log.exception("Reservation expiry transaction failed")
                await asyncio.sleep(5)
    finally:
        await database.engine.dispose()


if __name__ == "__main__":
    asyncio.run(run())
