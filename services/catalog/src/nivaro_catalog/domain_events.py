from datetime import datetime
from uuid import uuid4

from nivaro_catalog.domain.checkout import Quote
from nivaro_catalog.infrastructure.models import OutboxRow, ReservationRow

RESERVATION_EXPIRED = "inventory.reservation.expired"
EVENT_EXCHANGE = "nivaro.events"


def reservation_expired(row: ReservationRow, quote: Quote, occurred_at: datetime) -> OutboxRow:
    event_id = uuid4()
    return OutboxRow(
        id=event_id,
        event_type=RESERVATION_EXPIRED,
        aggregate_id=row.operation_id,
        aggregate_version=row.version,
        created_at=occurred_at,
        available_at=occurred_at,
        envelope={
            "event_id": str(event_id),
            "event_type": RESERVATION_EXPIRED,
            "schema_version": 1,
            "occurred_at": occurred_at.isoformat(),
            "producer": "catalog",
            "aggregate_id": str(row.operation_id),
            "aggregate_version": row.version,
            "correlation_id": str(row.operation_id),
            "causation_id": None,
            "payload": {
                "quote_id": str(row.quote_id),
                "market": quote.market,
                "currency": quote.currency,
                "expires_at": row.expires_at.isoformat(),
            },
        },
    )
