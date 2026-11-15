import hashlib
import json
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from nivaro_payments.contracts import (
    AttemptState,
    CompensationIntent,
    PaymentError,
    PaymentIntent,
    RefundIntent,
)
from nivaro_payments.events import Outcome, outcome, refund_completed
from nivaro_payments.models import Attempt, Refund
from nivaro_payments.provider import Provider, ProviderAttempt

RECONCILIATION_LIMIT = 8
OUTCOMES: dict[AttemptState, Outcome] = {
    "failed": "payment.failed",
    "succeeded": "payment.succeeded",
    "amount_mismatch": "payment.amount_mismatch",
}


def fingerprint(body: dict[str, object]) -> str:
    return hashlib.sha256(
        json.dumps(body, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


async def database_time(db: AsyncSession) -> datetime:
    now: datetime = (await db.execute(select(func.clock_timestamp()))).scalar_one()
    return now


async def read_attempt(db: AsyncSession, attempt_id: UUID, *, lock: bool = False) -> Attempt:
    row = await db.get(Attempt, attempt_id, with_for_update=lock)
    if row is None:
        raise PaymentError("payment.not_found", 404)
    return row


async def start_payment(
    db: AsyncSession, provider: Provider, key: str, body: PaymentIntent
) -> Attempt:
    deadline = body.reservation_expires_at.astimezone(UTC)
    fields = body.model_dump()
    fields["reservation_expires_at"] = deadline
    digest = fingerprint(
        {
            **body.model_dump(mode="json"),
            "reservation_expires_at": deadline.isoformat(),
        }
    )
    async with db.begin():
        inserted = await db.scalar(
            insert(Attempt)
            .values(
                **fields,
                idempotency_key=key,
                fingerprint=digest,
                provider_reference=provider.create_payment(body),
                status="pending",
                version=1,
            )
            .on_conflict_do_nothing()
            .returning(Attempt.id)
        )
        if inserted is not None:
            if body.reservation_expires_at < (await database_time(db)) + timedelta(seconds=90):
                raise PaymentError("payment.reservation_too_short")
            return await read_attempt(db, inserted)
        existing = await db.scalar(select(Attempt).where(Attempt.idempotency_key == key))
        if existing is None or (existing.id, existing.fingerprint) != (body.id, digest):
            raise PaymentError("payment.idempotency_conflict")
        return existing


def provider_attempt(row: Attempt) -> ProviderAttempt:
    return ProviderAttempt(
        row.id,
        row.order_id,
        row.provider_reference,
        row.currency,
        row.amount_minor,
        row.scenario,
        row.created_at,
    )


def apply_observation(
    db: AsyncSession, provider: Provider, row: Attempt, now: datetime, *, query: bool
) -> None:
    attempt = provider_attempt(row)
    report = (
        provider.query_payment(attempt, now) if query else provider.verify_payment(attempt, now)
    )
    if (report.reference, report.order_id, report.currency) != (
        row.provider_reference,
        row.order_id,
        row.currency,
    ):
        raise PaymentError("provider.evidence_mismatch", 502)
    state: AttemptState = report.state
    captured = report.captured_minor
    if report.state == "succeeded":
        if (
            captured is None
            or not 0 < captured <= 9_000_000_000_000_010
            or (row.currency == "IRR" and captured % 10)
        ):
            raise PaymentError("provider.evidence_mismatch", 502)
        if captured != row.amount_minor:
            state = "amount_mismatch"
    elif captured is not None:
        raise PaymentError("provider.evidence_mismatch", 502)
    if state != row.status:
        row.status = state
        row.version += 1
    name = OUTCOMES.get(state)
    if name is not None:
        row.verified_at = now
        row.captured_minor = captured
        row.reconcile_at = None
        db.add(outcome(row, name, now))


async def verify_payment(db: AsyncSession, provider: Provider, attempt_id: UUID) -> Attempt:
    unavailable: PaymentError | None = None
    async with db.begin():
        row = await read_attempt(db, attempt_id, lock=True)
        if row.verified_at is not None:
            return row
        now = await database_time(db)
        try:
            apply_observation(db, provider, row, now, query=row.status == "ambiguous")
        except PaymentError as exc:
            if exc.code != "provider.unavailable":
                raise
            unavailable = exc
        if (
            row.verified_at is None
            and row.reconcile_at is None
            and row.reconciliation_attempts < RECONCILIATION_LIMIT
        ):
            row.reconcile_at = now + timedelta(seconds=2)
    if unavailable is not None:
        raise unavailable
    return row


async def reconcile_one(db: AsyncSession, provider: Provider) -> bool:
    async with db.begin():
        row = await db.scalar(
            select(Attempt)
            .where(
                Attempt.reconcile_at <= func.statement_timestamp(), Attempt.verified_at.is_(None)
            )
            .order_by(Attempt.reconcile_at, Attempt.id)
            .limit(1)
            .with_for_update(skip_locked=True)
        )
        if row is None:
            return False
        now = await database_time(db)
        row.reconciliation_attempts += 1
        try:
            apply_observation(db, provider, row, now, query=True)
        except PaymentError as exc:
            if exc.code not in {"provider.unavailable", "provider.evidence_mismatch"}:
                raise
        if row.verified_at is None:
            if row.reconciliation_attempts < RECONCILIATION_LIMIT:
                row.reconcile_at = now + timedelta(seconds=min(60, 2**row.reconciliation_attempts))
            else:
                row.reconcile_at = None
        return True


async def refund_replay(
    db: AsyncSession, key: str, refund_id: UUID, payment_id: UUID, digest: str
) -> Refund | None:
    existing = (
        await db.scalars(
            select(Refund).where(or_(Refund.id == refund_id, Refund.idempotency_key == key))
        )
    ).all()
    if not existing:
        return None
    if len(existing) == 1:
        row = existing[0]
        if (row.id, row.idempotency_key, row.payment_id, row.fingerprint) == (
            refund_id,
            key,
            payment_id,
            digest,
        ):
            return row
    raise PaymentError("refund.idempotency_conflict")


async def refund_payment(
    db: AsyncSession,
    provider: Provider,
    payment_id: UUID,
    key: str,
    body: RefundIntent | CompensationIntent,
) -> Refund:
    digest = fingerprint(body.model_dump(mode="json"))
    async with db.begin():
        # Serializes all refund amount decisions for this captured payment.
        payment = await read_attempt(db, payment_id, lock=True)
        existing = await refund_replay(db, key, body.id, payment_id, digest)
        if existing is not None:
            return existing
        if body.currency != payment.currency:
            raise PaymentError("refund.currency_or_amount")
        if payment.captured_minor is None:
            raise PaymentError("refund.not_captured")
        refunded = (
            await db.scalar(
                select(func.sum(Refund.amount_minor)).where(Refund.payment_id == payment_id)
            )
        ) or 0
        # PostgreSQL returns NUMERIC from SUM(bigint), even for integral minor units.
        remaining = payment.captured_minor - int(refunded)
        if isinstance(body, CompensationIntent):
            if (body.order_id, body.captured_minor) != (payment.order_id, payment.captured_minor):
                raise PaymentError("refund.capture_mismatch")
            if remaining == 0:
                raise PaymentError("refund.already_refunded")
            request = RefundIntent(
                id=body.id, currency=body.currency, amount_minor=remaining, reason=body.reason
            )
        else:
            request = body
        if request.currency == "IRR" and request.amount_minor % 10:
            raise PaymentError("refund.currency_or_amount")
        if request.amount_minor > remaining:
            raise PaymentError("refund.exceeds_capture")
        row: Refund | None = await db.scalar(
            insert(Refund)
            .values(
                **request.model_dump(),
                payment_id=payment_id,
                idempotency_key=key,
                fingerprint=digest,
                provider_reference=provider.refund_payment(provider_attempt(payment), request),
            )
            .on_conflict_do_nothing()
            .returning(Refund)
        )
        if row is None:
            existing = await refund_replay(db, key, request.id, payment_id, digest)
            if existing is None:
                raise PaymentError("refund.idempotency_conflict")
            return existing
        db.add(refund_completed(payment, row))
        return row
