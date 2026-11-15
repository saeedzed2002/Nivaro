"""Record deliveries and project verified-purchase eligibility."""

import sqlalchemy as sa
from alembic import op

revision = "0010_purchase_entitlements"
down_revision = "0009_paid_reservation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "delivered_order_inbox",
        sa.Column("event_id", sa.Uuid(), primary_key=True),
        sa.Column("order_id", sa.Uuid(), nullable=False, unique=True),
        sa.Column("fingerprint", sa.String(64), nullable=False),
    )
    op.create_table(
        "purchase_entitlements",
        sa.Column("customer_id", sa.Uuid(), primary_key=True),
        sa.Column("product_id", sa.Uuid(), primary_key=True),
        sa.Column("first_delivered_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    raise RuntimeError("Downgrading would discard verified-purchase evidence")
