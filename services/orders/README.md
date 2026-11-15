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
JSON list `ORDERS_DELIVERY_RATES`. Each entry specifies `market`, `currency`,
`country`, `policy_version`, `shipping_minor`, `tax_basis_points`,
`tax_included` and `shipping_taxable`. The default list is empty. A missing
destination policy blocks confirmation. Each confirmed order records that
policy along with its amounts. IRR discounts and calculated tax round down to
whole tomans. USD amounts use cents. Tests use synthetic rates and coupons.

The service starts with `compose.orders.yaml` and exposes its two health
routes on the project network. Its reservation worker claims a short database
lease on a pending order before calling Catalog. The worker looks up the
original operation ID before requesting a hold. An ambiguous response leaves
the order pending for retry with bounded backoff. A live Catalog receipt moves
the order to `awaiting_payment` and aligns the coupon claim's deadline with the
stock hold. A definite rejection or expiry closes the order and releases its
coupon claim. Checkout HTTP routes and the storefront will wire into the
existing checkout application use cases in the next checkpoint.

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
