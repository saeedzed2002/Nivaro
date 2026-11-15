import asyncio
import os
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import httpx
import psycopg
import pytest

from nivaro_payments.contracts import PaymentError
from nivaro_payments.provider import ProviderAttempt, Simulator
from nivaro_payments.settings import Settings

NOW = datetime(2026, 1, 1, tzinfo=UTC)
ROOT = "/internal/v1/payments/attempts"
integration = pytest.mark.skipif(
    os.getenv("PAYMENTS_E2E") != "1", reason="Disposable payments stack required"
)


@pytest.mark.parametrize(
    ("scenario", "wait", "expected", "capture"),
    [
        ("success", 0, "succeeded", 1000),
        ("failure", 0, "failed", None),
        ("ambiguous", 4, "ambiguous", None),
        ("ambiguous", 5, "succeeded", 1000),
        ("delay", 29, "pending", None),
        ("delay", 30, "succeeded", 1000),
        ("duplicate", 0, "succeeded", 1000),
        ("overpayment", 0, "succeeded", 1010),
    ],
)
def test_simulator_reports_deterministic_iran_evidence(scenario, wait, expected, capture):
    provider = Simulator()
    attempt = ProviderAttempt(uuid4(), uuid4(), "fixture", "IRR", 1000, scenario, NOW)
    observation = provider.verify_payment(attempt, NOW + timedelta(seconds=wait))
    assert observation == provider.query_payment(attempt, NOW + timedelta(seconds=wait))
    assert (observation.state, observation.captured_minor, observation.order_id) == (
        expected,
        capture,
        attempt.order_id,
    )


def test_unavailable_provider_reports_no_financial_outcome():
    attempt = ProviderAttempt(uuid4(), uuid4(), "fixture", "USD", 1000, "unavailable", NOW)
    with pytest.raises(PaymentError, match="provider.unavailable") as failure:
        Simulator().verify_payment(attempt, NOW)
    assert failure.value.status == 503


def intent(currency="IRR", *, scenario="success", hold=600):
    return {
        "id": str(uuid4()),
        "order_id": str(uuid4()),
        "order_version": 2,
        "market": "ir" if currency == "IRR" else "international",
        "currency": currency,
        "amount_minor": 1000,
        "scenario": scenario,
        "reservation_expires_at": (datetime.now(UTC) + timedelta(seconds=hold)).isoformat(),
    }


@pytest.fixture
async def clients():
    secret_path = Settings().db_password_file.with_name("orders_client_secret")
    async with (
        httpx.AsyncClient(base_url="http://payments:8000", timeout=15) as payments,
        httpx.AsyncClient(base_url="http://identity:8000", timeout=10) as identity,
    ):
        yield payments, identity, secret_path.read_text(encoding="utf-8").strip()


async def grant(clients, scope, *, audience="nivaro-payments", **extra):
    _, identity, key = clients
    return await identity.post(
        "/internal/v1/service-tokens",
        auth=("orders", key),
        json={"audience": audience, "scope": scope, **extra},
    )


async def headers(clients, scope, key=None, *, audience="nivaro-payments"):
    response = await grant(clients, scope, audience=audience)
    assert response.status_code == 200, response.text
    result = {"Authorization": "Bearer " + response.json()["access_token"]}
    if key is not None:
        result["Idempotency-Key"] = key
    return result


def expect(response, status=200, *, code=None):
    assert response.status_code == status, response.text
    body = response.json()
    if code:
        assert body["error"]["code"] == code
    return body


@integration
async def test_payment_authorization_and_network_boundary(clients):
    payments, _, _ = clients
    body = intent()
    assert (await grant(clients, "payments.other")).status_code == 403
    assert (await grant(clients, "payments.start", audience="nivaro-catalog")).status_code == 403
    assert (await grant(clients, "payments.start", customer_access="delegated")).status_code == 403
    expect(
        await payments.post(ROOT, headers={"Idempotency-Key": "no-token"}, json=body),
        401,
        code="service.unauthorized",
    )
    wrong_scope = await headers(clients, "payments.read", "read-only")
    expect(await payments.post(ROOT, headers=wrong_scope, json=body), 403, code="service.forbidden")
    wrong_audience = await headers(
        clients, "catalog.quote", "catalog-only", audience="nivaro-catalog"
    )
    expect(
        await payments.post(ROOT, headers=wrong_audience, json=body),
        401,
        code="service.unauthorized",
    )
    valid = await headers(clients, "payments.start", "invalid-amount")
    expect(await payments.post(ROOT, headers=valid, json={**body, "currency": "USD"}), 422)
    expect(
        await payments.post(ROOT, headers={**valid, "Idempotency-Key": "bad key"}, json=body), 422
    )
    expect(await payments.post(ROOT, headers=valid, json={**body, "amount_minor": 1001}), 422)
    expect(
        await payments.post(
            ROOT, headers=valid, json={**body, "redirect_url": "https://example.test"}
        ),
        422,
    )
    expect(await payments.get(f"{ROOT}/{body['id']}", headers=wrong_scope), 404)
    async with httpx.AsyncClient(base_url="http://gateway:8080", timeout=10) as gateway:
        hidden = await gateway.post(ROOT, headers=valid, json=body)
        assert hidden.status_code == 404 and hidden.content == b""
    settings = Settings()
    assert settings.db_host.startswith("nivaro-payments-qa-")
    with pytest.raises(psycopg.OperationalError, match="permission denied"):
        await psycopg.AsyncConnection.connect(
            host=settings.db_host,
            dbname="nivaro_catalog",
            user=settings.db_user,
            password=settings.db_password_file.read_text().strip(),
        )


@integration
@pytest.mark.parametrize("currency", ["IRR", "USD"])
async def test_concurrent_start_and_verify_share_one_persisted_attempt(clients, currency):
    payments, _, _ = clients
    body = intent(currency, scenario="duplicate")
    auth = await headers(clients, "payments.start", str(uuid4()))
    replies = await asyncio.gather(
        *(payments.post(ROOT, headers=auth, json=body) for _ in range(12))
    )
    created = expect(replies[0])
    assert all(expect(response) == created for response in replies)
    assert (created["id"], created["status"], created["version"], created["captured_minor"]) == (
        body["id"],
        "pending",
        1,
        None,
    )
    assert created["provider_reference"].startswith("sim-" + currency.lower() + "-")
    expect(
        await payments.post(ROOT, headers=auth, json={**body, "amount_minor": 1100}),
        409,
        code="payment.idempotency_conflict",
    )
    expect(
        await payments.post(ROOT, headers={**auth, "Idempotency-Key": str(uuid4())}, json=body),
        409,
        code="payment.idempotency_conflict",
    )
    path = f"{ROOT}/{body['id']}"
    read = await headers(clients, "payments.read")
    assert expect(await payments.get(path, headers=read)) == created
    verify = await headers(clients, "payments.verify")
    answers = await asyncio.gather(
        *(payments.post(path + "/verify", headers=verify) for _ in range(8))
    )
    verified = expect(answers[0])
    assert all(expect(response) == verified for response in answers)
    assert (
        verified["currency"],
        verified["status"],
        verified["captured_minor"],
        verified["version"],
    ) == (currency, "succeeded", 1000, 2)
    assert verified["verified_at"] is not None
    assert expect(await payments.get(path, headers=read)) == verified


@integration
async def test_unknown_results_remain_unsettled_and_mismatches_are_visible(clients):
    payments, _, _ = clients
    start = await headers(clients, "payments.start")
    verify = await headers(clients, "payments.verify")
    read = await headers(clients, "payments.read")

    short = intent(hold=60)
    expect(
        await payments.post(ROOT, headers={**start, "Idempotency-Key": str(uuid4())}, json=short),
        409,
        code="payment.reservation_too_short",
    )
    expect(await payments.get(f"{ROOT}/{short['id']}", headers=read), 404)
    for scenario, status, capture in [
        ("delay", "pending", None),
        ("failure", "failed", None),
        ("overpayment", "amount_mismatch", 1001),
        ("unavailable", "pending", None),
    ]:
        body = intent("USD", scenario=scenario)
        expect(
            await payments.post(ROOT, headers={**start, "Idempotency-Key": str(uuid4())}, json=body)
        )
        path = f"{ROOT}/{body['id']}"
        response = await payments.post(path + "/verify", headers=verify)
        if scenario == "unavailable":
            expect(response, 503, code="provider.unavailable")
        else:
            expect(response)
        current = expect(await payments.get(path, headers=read))
        assert (current["status"], current["captured_minor"]) == (status, capture)
        assert (current["verified_at"] is None) == (status == "pending")


@integration
@pytest.mark.parametrize("currency", ["IRR", "USD"])
async def test_concurrent_refunds_preserve_capture_limit_and_currency(clients, currency):
    payments, _, _ = clients
    body = intent(currency)
    expect(
        await payments.post(
            ROOT, headers=await headers(clients, "payments.start", str(uuid4())), json=body
        )
    )
    path = f"{ROOT}/{body['id']}"
    refund_auth = await headers(clients, "payments.refund")

    async def refund(amount, refund_currency=currency, request_id=None):
        key = request_id or str(uuid4())
        return await payments.post(
            path + "/refunds",
            headers={**refund_auth, "Idempotency-Key": key},
            json={
                "id": key,
                "currency": refund_currency,
                "amount_minor": amount,
                "reason": "test_refund",
            },
        )

    expect(await refund(200), 409, code="refund.not_captured")
    expect(await payments.post(path + "/verify", headers=await headers(clients, "payments.verify")))
    expect(
        await refund(200, "USD" if currency == "IRR" else "IRR"),
        409,
        code="refund.currency_or_amount",
    )
    if currency == "IRR":
        expect(await refund(201), 409, code="refund.currency_or_amount")
    replies = await asyncio.gather(*(refund(600) for _ in range(8)))
    (accepted,) = [expect(response) for response in replies if response.status_code == 200]
    for response in replies:
        if response.status_code != 200:
            expect(response, 409, code="refund.exceeds_capture")
    assert accepted["currency"] == currency and accepted["simulated"] is True
    assert expect(await refund(600, request_id=accepted["id"])) == accepted
    expect(await refund(400, request_id=accepted["id"]), 409, code="refund.idempotency_conflict")
    assert expect(await refund(400))["amount_minor"] == 400
