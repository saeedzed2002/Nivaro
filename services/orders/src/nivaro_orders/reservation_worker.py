"""Recover pending checkout operations without depending on an active HTTP request."""

import asyncio
import logging

import httpx
from sqlalchemy.exc import SQLAlchemyError

from nivaro_orders.application.payment_compensation import advance_refund, schedule_compensation
from nivaro_orders.application.payment_finalization import advance_payment_stock, prepare_payment
from nivaro_orders.application.payment_initiation import advance_customer_payment
from nivaro_orders.application.reservations import advance_reservation, expire_unpaid
from nivaro_orders.infrastructure.database import Database
from nivaro_orders.infrastructure.payment_compensations import PaymentCompensations
from nivaro_orders.infrastructure.reservations import CatalogReservations
from nivaro_orders.infrastructure.simulator_payments import SimulatorPayments
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
            payments = PaymentCompensations(http, settings, secret)
            simulator = SimulatorPayments(http, settings, secret)
            while True:
                try:
                    async with database.sessions() as db:
                        for _ in range(10):
                            if not await prepare_payment(db):
                                break
                        for _ in range(10):
                            if not await schedule_compensation(db):
                                break
                        for _ in range(20):
                            if not await expire_unpaid(db):
                                break
                    for _ in range(10):
                        if not await advance_payment_stock(database.sessions, catalog):
                            break
                    for _ in range(5):
                        if not await advance_refund(database.sessions, payments):
                            break
                    for _ in range(3):
                        if not await advance_customer_payment(
                            database.sessions, catalog, simulator
                        ):
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
