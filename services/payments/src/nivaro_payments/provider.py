from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Literal, Protocol
from uuid import UUID

from nivaro_payments.contracts import Currency, PaymentError, PaymentIntent, RefundIntent, Scenario


@dataclass(frozen=True)
class ProviderAttempt:
    id: UUID
    order_id: UUID
    reference: str
    currency: Currency
    amount_minor: int
    scenario: Scenario
    created_at: datetime


@dataclass(frozen=True)
class Evidence:
    reference: str
    order_id: UUID
    currency: Currency
    state: Literal["pending", "ambiguous", "failed", "succeeded"]
    captured_minor: int | None = None


class Provider(Protocol):
    def create_payment(self, intent: PaymentIntent) -> str: ...
    def verify_payment(self, attempt: ProviderAttempt, now: datetime) -> Evidence: ...
    def query_payment(self, attempt: ProviderAttempt, now: datetime) -> Evidence: ...
    def refund_payment(self, attempt: ProviderAttempt, intent: RefundIntent) -> str: ...


class Simulator:
    def create_payment(self, intent: PaymentIntent) -> str:
        return f"sim-{intent.currency.lower()}-{intent.id.hex}"

    def verify_payment(self, attempt: ProviderAttempt, now: datetime) -> Evidence:
        return self.query_payment(attempt, now)

    def query_payment(self, attempt: ProviderAttempt, now: datetime) -> Evidence:
        reference, order_id, currency = attempt.reference, attempt.order_id, attempt.currency
        match attempt.scenario:
            case "unavailable":
                raise PaymentError("provider.unavailable", 503)
            case "failure":
                return Evidence(reference, order_id, currency, "failed")
            case "ambiguous" if now < attempt.created_at + timedelta(seconds=5):
                return Evidence(reference, order_id, currency, "ambiguous")
            case "delay" if now < attempt.created_at + timedelta(seconds=30):
                return Evidence(reference, order_id, currency, "pending")
            case "overpayment":
                quantum = 10 if currency == "IRR" else 1
                return Evidence(
                    reference, order_id, currency, "succeeded", attempt.amount_minor + quantum
                )
            case _:
                # Success and duplicate deliveries emit the identical provider receipt.
                return Evidence(reference, order_id, currency, "succeeded", attempt.amount_minor)

    def refund_payment(self, attempt: ProviderAttempt, intent: RefundIntent) -> str:
        return f"sim-refund-{attempt.currency.lower()}-{intent.id.hex}"
