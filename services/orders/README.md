# Nivaro Orders

Orders owns a separate PostgreSQL database. The first migration stores checkout
operations, pending orders, address/item/configuration snapshots, order
transitions, coupons and coupon claims. External customer, product, quote and
cart references remain identifiers.

The application first creates a durable checkout operation with a
customer-scoped idempotency key and fingerprint of the actual intent. It
accepts only the trusted catalog quote and version-bound address snapshot from
service callers. Pricing returns a confirmation fingerprint. Staging with a
changed address, quote or monetary policy requires a new review. Staging also
holds the coupon row while checking and claiming its quota in the same
transaction that records the order.

Shipping and tax are configured per market and destination country using the
JSON list `ORDERS_DELIVERY_RATES`, passed by Compose from
`NIVARO_ORDERS_DELIVERY_RATES`. Each entry specifies `market`, `currency`,
`country`, `policy_version`, `shipping_minor`, `tax_basis_points`,
`tax_included` and `shipping_taxable`. The default list is empty. A missing
destination policy blocks confirmation. Each confirmed order records that
policy along with its amounts. An Iran rate can include
`free_shipping_threshold_minor` in rials. The amount must be in whole tomans.
Shipping is waived when the merchandise subtotal after coupon discounts reaches
the threshold. Taxable shipping uses the actual fee after applying the policy.
Omit the threshold to use the flat fee. IRR discounts and calculated tax round
down to whole tomans. USD amounts use cents. Tests use synthetic rates and coupons.

The service starts with `compose.orders.yaml` and exposes its two health
routes on the project network. Its reservation worker claims a short database
lease on a pending order before calling Catalog. The worker looks up the
original operation ID before requesting a hold. An ambiguous response leaves
the order pending for retry with bounded backoff. A live Catalog receipt moves
the order to `awaiting_payment` and aligns the coupon claim's deadline with the
stock hold. A definite rejection or expiry closes the order and releases its
coupon claim. The storefront obtains the reviewed amounts, submits the explicit
confirmation and reads the order's status through the Orders HTTP routes.

Run the foundation checks with tested release and test images.

```powershell
./scripts/Verify-OrdersFoundation.ps1 -WithCatalog
```

The script starts the release container, database-role initializer and
migration job on a separate temporary PostgreSQL project. It checks fresh
schema, Docker readiness, role isolation, money, idempotency and coupon
contention. The catalog option starts Identity and Catalog and uses their real
HTTP endpoints to test recovery after a successful reservation response is
lost.

## Durable reservation expiry

Use `compose.events.yaml` with the media and Orders overlays. The broker
initializer supplies a separate `commerce-events` vhost and distinct Catalog
publisher and Orders consumer credentials. A broker already running with the
earlier definitions needs to reload the updated definitions before starting
the event workers. Keep all existing broker volumes and passwords.

Catalog releases stock and inserts the versioned
`inventory.reservation.expired` outbox envelope in the same database
transaction. It marks publication only after a persistent, routed message is
confirmed. Orders stores its inbox identifier and expiry effect together and
acknowledges after that transaction commits. The envelope carries the checkout
operation, quote, market, currency and deadline. Unmatched or stale events
cannot change a newer hold.

The expiry queue bounds redelivery and transfers exhausted or malformed
messages to its durable error queue. [RabbitMQ quorum queue documentation](https://www.rabbitmq.com/docs/quorum-queues)

- Inspect outbox lag with the oldest `created_at` whose `published_at` is
  null. Inspect terminal failures by `failed_at` and `last_error`. A broker
  operator can check pending and error queue depths on `commerce-events`
  with `rabbitmqctl list_queues -p commerce-events name messages`.
- Once the publisher fault is corrected, replay a specific failed outbox
  record by resetting `attempts`, `failed_at` and `available_at` only for
  its event ID with no active lease and no publication timestamp. Keep its
  original event ID and envelope. For a valid dead-lettered message, replay
  to the original routing key with the original message ID, and acknowledge
  the error-queue copy only after the rerouted message is confirmed.
- Run `./scripts/Verify-OrdersFoundation.ps1 -WithEvents` with the current
  service images to verify real publishing, handling and dead-lettering on a
  disposable broker and databases.
