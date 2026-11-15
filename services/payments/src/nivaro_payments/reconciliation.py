import asyncio
import logging

from sqlalchemy.exc import SQLAlchemyError

from nivaro_payments.attempts import reconcile_one
from nivaro_payments.provider import Simulator
from nivaro_payments.settings import Database, Settings

log = logging.getLogger(__name__)


async def run() -> None:
    database = Database(Settings())
    provider = Simulator()
    try:
        while True:
            try:
                async with database.sessions() as db:
                    for _ in range(20):
                        if not await reconcile_one(db, provider):
                            break
                    else:
                        await asyncio.sleep(0.1)
                        continue
            except SQLAlchemyError:
                log.exception("Payments reconciliation database operation failed")
            await asyncio.sleep(2)
    finally:
        await database.engine.dispose()


if __name__ == "__main__":
    asyncio.run(run())
