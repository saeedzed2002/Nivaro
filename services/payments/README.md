# Nivaro Payments

Payments owns `nivaro_payments` and a restricted database role. The private
simulator records the Orders attempt ID, order version, market, currency,
expected amount, provider reference and observed result. PostgreSQL serializes
writes and retains the idempotency keys. The local provider runs in process and
its observations are reproducible from the immutable attempt and database time.

Identity issues separate 30-second Orders grants for the `nivaro-payments`
audience. The public gateway denies `/internal/*` and the Payments container
has no published host port.

| Method and path under `/internal/v1/payments` | Required scope | Behavior |
| --- | --- | --- |
| `POST /attempts` | `payments.start` | Bind an `Idempotency-Key` to the actual Orders intent. Requires at least 90 seconds left on a new attempt's reservation. |
| `GET /attempts/{attempt_id}` | `payments.read` | Read the persisted status and captured amount, if any. |
| `POST /attempts/{attempt_id}/verify` | `payments.verify` | Ask the simulator for evidence and apply a matching result once. An ambiguous attempt is queried on retry. |
| `POST /attempts/{attempt_id}/refunds` | `payments.refund` | Complete a simulated refund using a separate key. Concurrent refunds share one capture limit. |

Supported scenarios are `success`, `failure`, `ambiguous`, `duplicate`, `delay`,
`overpayment` and `unavailable`. Ambiguity resolves after 5 seconds and delay
after 30 seconds when queried again. Overpayment records `amount_mismatch` with
the actual simulated amount. Duplicate verification keeps the original receipt
and version. Unavailability yields a retryable response and preserves the
last persisted result. The Orders integration will own when to verify an
attempt and how to apply payment events and compensation.

`IRR` amounts are expressed in rials in whole tomans. `USD` amounts are in
cents. Refunds use the original currency and the verified captured amount as
their upper bound. The database contains simulator records only.

Build `nivaro-payments:release` and `nivaro-payments:test` from the pinned
Dockerfile, then run the foundation check from the repository root.

```powershell
./scripts/Verify-PaymentsFoundation.ps1
```

The check uses a disposable Compose project with real Identity tokens and
separate PostgreSQL databases. Local development uses `compose.payments.yaml`
with the existing overlays and secret initializer.
