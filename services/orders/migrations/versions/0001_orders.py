"""Initial Orders database, immutable snapshots, and coupon claims."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0001_orders"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "checkout_operations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("customer_id", sa.Uuid(), nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("fingerprint", sa.String(length=64), nullable=False),
        sa.Column("intent", postgresql.JSONB(), nullable=False),
        sa.Column("state", sa.String(length=24), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("state IN ('started','pending_reservation')", name="checkout_state"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("customer_id", "idempotency_key", name="uq_checkout_customer_key"),
    )
    op.create_table(
        "coupons",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("code", sa.String(length=40), nullable=False),
        sa.Column("market", sa.String(length=20), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("kind", sa.String(length=10), nullable=False),
        sa.Column("value", sa.BigInteger(), nullable=False),
        sa.Column("minimum_minor", sa.BigInteger(), nullable=False),
        sa.Column("maximum_minor", sa.BigInteger(), nullable=True),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("global_limit", sa.Integer(), nullable=False),
        sa.Column("per_customer_limit", sa.Integer(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "(kind = 'fixed' AND value > 0) OR (kind = 'percentage' AND value BETWEEN 1 AND 10000)",
            name="coupon_discount_bounds",
        ),
        sa.CheckConstraint(
            "(market = 'ir' AND currency = 'IRR') OR (market = 'international' AND currency = 'USD')",
            name="coupon_market_currency",
        ),
        sa.CheckConstraint("code ~ '^[A-Z0-9][A-Z0-9_-]{0,39}$'", name="coupon_code"),
        sa.CheckConstraint(
            "currency <> 'IRR' OR ((kind <> 'fixed' OR value % 10 = 0) AND minimum_minor % 10 = 0 AND (maximum_minor IS NULL OR maximum_minor % 10 = 0))",
            name="coupon_whole_tomans",
        ),
        sa.CheckConstraint(
            "minimum_minor >= 0 AND (maximum_minor IS NULL OR maximum_minor > 0) AND global_limit >= per_customer_limit AND per_customer_limit > 0 AND starts_at < ends_at",
            name="coupon_policy_bounds",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("market", "code", name="uq_coupon_market_code"),
    )
    op.create_table(
        "orders",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("customer_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("cart_id", sa.Uuid(), nullable=False),
        sa.Column("cart_version", sa.Integer(), nullable=False),
        sa.Column("cart_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("quote_id", sa.Uuid(), nullable=False),
        sa.Column("quote_expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("confirmation", sa.String(length=64), nullable=False),
        sa.Column("market", sa.String(length=20), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("subtotal_minor", sa.BigInteger(), nullable=False),
        sa.Column("discount_minor", sa.BigInteger(), nullable=False),
        sa.Column("shipping_minor", sa.BigInteger(), nullable=False),
        sa.Column("tax_minor", sa.BigInteger(), nullable=False),
        sa.Column("tax_included", sa.Boolean(), nullable=False),
        sa.Column("total_minor", sa.BigInteger(), nullable=False),
        sa.Column("delivery_policy", postgresql.JSONB(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "(market = 'ir' AND currency = 'IRR') OR (market = 'international' AND currency = 'USD')",
            name="order_market_currency",
        ),
        sa.CheckConstraint(
            "currency <> 'IRR' OR (subtotal_minor % 10 = 0 AND discount_minor % 10 = 0 AND shipping_minor % 10 = 0 AND tax_minor % 10 = 0 AND total_minor % 10 = 0)",
            name="order_whole_tomans",
        ),
        sa.CheckConstraint(
            "status IN ('pending_reservation','awaiting_payment','expired','cancelled')",
            name="order_status",
        ),
        sa.CheckConstraint(
            "subtotal_minor > 0 AND discount_minor BETWEEN 0 AND subtotal_minor AND shipping_minor >= 0 AND tax_minor >= 0 AND total_minor >= 0 AND total_minor = subtotal_minor - discount_minor + shipping_minor + CASE WHEN tax_included THEN 0 ELSE tax_minor END",
            name="order_totals",
        ),
        sa.CheckConstraint("version > 0 AND cart_version > 0", name="order_versions"),
        sa.ForeignKeyConstraint(["id"], ["checkout_operations.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("quote_id"),
    )
    op.create_index(
        "ix_orders_customer_created", "orders", ["customer_id", "created_at", "id"], unique=False
    )
    op.create_table(
        "coupon_claims",
        sa.Column("order_id", sa.Uuid(), nullable=False),
        sa.Column("coupon_id", sa.Uuid(), nullable=False),
        sa.Column("customer_id", sa.Uuid(), nullable=False),
        sa.Column("state", sa.String(length=10), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("amount_minor", sa.BigInteger(), nullable=False),
        sa.Column("snapshot", postgresql.JSONB(), nullable=False),
        sa.CheckConstraint(
            "state IN ('held','consumed','released') AND amount_minor > 0",
            name="coupon_claim_state",
        ),
        sa.ForeignKeyConstraint(["coupon_id"], ["coupons.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["order_id"], ["orders.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("order_id"),
    )
    op.create_index(
        "ix_coupon_claims_usage",
        "coupon_claims",
        ["coupon_id", "state", "expires_at", "customer_id"],
        unique=False,
    )
    op.create_table(
        "order_address_snapshots",
        sa.Column("order_id", sa.Uuid(), nullable=False),
        sa.Column("snapshot", postgresql.JSONB(), nullable=False),
        sa.ForeignKeyConstraint(["order_id"], ["orders.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("order_id"),
    )
    op.create_table(
        "order_configuration_snapshots",
        sa.Column("order_id", sa.Uuid(), nullable=False),
        sa.Column("source_group_id", sa.Uuid(), nullable=False),
        sa.Column("snapshot", postgresql.JSONB(), nullable=False),
        sa.ForeignKeyConstraint(["order_id"], ["orders.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("order_id", "source_group_id"),
    )
    op.create_table(
        "order_transitions",
        sa.Column("order_id", sa.Uuid(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("customer_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("reason", sa.String(length=80), nullable=False),
        sa.Column(
            "occurred_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["order_id"], ["orders.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("order_id", "version"),
    )
    op.create_table(
        "order_items",
        sa.Column("order_id", sa.Uuid(), nullable=False),
        sa.Column("source_line_id", sa.Uuid(), nullable=False),
        sa.Column("source_line_version", sa.Integer(), nullable=False),
        sa.Column("source_group_id", sa.Uuid(), nullable=True),
        sa.Column("slot_key", sa.String(length=32), nullable=True),
        sa.Column("product_id", sa.Uuid(), nullable=False),
        sa.Column("variant_id", sa.Uuid(), nullable=False),
        sa.Column("sku", sa.String(length=100), nullable=False),
        sa.Column("name", sa.String(length=240), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("unit_price_minor", sa.BigInteger(), nullable=False),
        sa.Column("spec_version", sa.Integer(), nullable=False),
        sa.Column("specifications", postgresql.JSONB(), nullable=False),
        sa.Column("price_version", sa.Integer(), nullable=False),
        sa.CheckConstraint(
            "(source_group_id IS NULL) = (slot_key IS NULL)", name="order_item_slot_scope"
        ),
        sa.CheckConstraint(
            "quantity > 0 AND unit_price_minor > 0 AND source_line_version > 0",
            name="order_item_positive",
        ),
        sa.ForeignKeyConstraint(
            ["order_id", "source_group_id"],
            [
                "order_configuration_snapshots.order_id",
                "order_configuration_snapshots.source_group_id",
            ],
            name="order_item_configuration",
        ),
        sa.ForeignKeyConstraint(["order_id"], ["orders.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("order_id", "source_line_id"),
    )


def downgrade() -> None:
    raise RuntimeError("The initial Orders schema has no data-destructive downgrade")
