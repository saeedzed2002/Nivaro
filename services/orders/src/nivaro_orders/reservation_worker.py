"""Recover pending checkout operations without depending on an active HTTP request."""

import asyncio
import logging

import httpx
from sqlalchemy.exc import SQLAlchemyError

from nivaro_orders.application.reservations import advance_reservation, expire_unpaid
from nivaro_orders.infrastructure.database import Database
from nivaro_orders.infrastructure.reservations import CatalogReservations
from nivaro_orders.settings import Settings

log = logging.getLogger(__name__)


async def run() -> None:
    settings = Settings()
    secret = settings.client_secret_file.read_text(encoding="utf-8").strip()
    if len(secret) < 32:
        raise ValueError("Orders service credential is missing or invalid")
    database = Database(settings)
    try:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(5, connect=2), trust_env=False, follow_redirects=False
        ) as http:
            catalog = CatalogReservations(http, settings, secret)
            while True:
                try:
                    async with database.sessions() as db:
                        for _ in range(20):
                            if not await expire_unpaid(db):
                                break
                    for _ in range(10):
                        if not await advance_reservation(database.sessions, catalog):
                            break
                    else:
                        await asyncio.sleep(0.1)
                        continue
                except SQLAlchemyError:
                    log.exception("Orders reservation recovery database operation failed")
                await asyncio.sleep(2)
    finally:
        await database.engine.dispose()


if __name__ == "__main__":
    asyncio.run(run())
