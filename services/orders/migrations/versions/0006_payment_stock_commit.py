"""Track the one selected capture and recover stock commits by order ID."""

import sqlalchemy as sa
from alembic import op

revision = "0006_payment_stock_commit"
down_revision = "0005_order_payment_results"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint("order_status", "orders", type_="check")
    op.create_check_constraint(
        "order_status",
        "orders",
        "status IN ('pending_reservation','awaiting_payment','expired','cancelled',"
        "'payment_processing','payment_review','paid')",
    )
    op.drop_constraint("coupon_claim_state", "coupon_claims", type_="check")
    op.create_check_constraint(
        "coupon_claim_state",
        "coupon_claims",
        "state IN ('held','finalizing','consumed','released') AND amount_minor > 0",
    )
    table = "order_payment_attempts"
    op.add_column(table, sa.Column("disposition", sa.String(80)))
    op.add_column(table, sa.Column("stock_retry_at", sa.DateTime(timezone=True)))
    op.add_column(
        table, sa.Column("stock_attempts", sa.Integer(), server_default="0", nullable=False)
    )
    op.create_check_constraint(
        "order_payment_stock_retry",
        table,
        "stock_attempts >= 0 AND (stock_retry_at IS NULL OR disposition IS NOT DISTINCT FROM 'selected')",
    )
    op.create_index(
        "ix_order_payment_unhandled",
        table,
        ["verified_at", "id"],
        postgresql_where=sa.text("disposition IS NULL AND captured_minor IS NOT NULL"),
    )
    op.create_index(
        "uq_order_payment_selected",
        table,
        ["order_id"],
        unique=True,
        postgresql_where=sa.text("disposition = 'selected'"),
    )
    op.create_index(
        "ix_order_payment_stock_due",
        table,
        ["stock_retry_at", "id"],
        postgresql_where=sa.text("stock_retry_at IS NOT NULL"),
    )


def downgrade() -> None:
    raise RuntimeError("Downgrading would discard stock finalization history")
