"""Persist authoritative quotes and atomic inventory allocations."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0007_checkout_inventory"
down_revision = "0006_public_cache"
branch_labels = None
depends_on = None


def timestamps():
    return [
        sa.Column(name, sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now())
        for name in ("created_at", "updated_at")
    ]


def upgrade():
    op.create_table(
        "checkout_quotes",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("snapshot", JSONB(), nullable=False),
        *timestamps(),
    )
    op.create_table(
        "stock_reservations",
        sa.Column("operation_id", sa.Uuid(), primary_key=True),
        sa.Column(
            "quote_id",
            sa.Uuid(),
            sa.ForeignKey("checkout_quotes.id", ondelete="RESTRICT"),
            unique=True,
            nullable=False,
        ),
        sa.Column("state", sa.String(12), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "state IN ('held','committed','released','expired')", name="reservation_state"
        ),
        *timestamps(),
    )
    op.create_index(
        "ix_reservations_held_expiry",
        "stock_reservations",
        ["expires_at", "operation_id"],
        postgresql_where=sa.text("state = 'held'"),
    )
    op.create_table(
        "stock_allocations",
        sa.Column(
            "operation_id",
            sa.Uuid(),
            sa.ForeignKey("stock_reservations.operation_id", ondelete="RESTRICT"),
            primary_key=True,
        ),
        sa.Column(
            "variant_id",
            sa.Uuid(),
            sa.ForeignKey("variants.id", ondelete="RESTRICT"),
            primary_key=True,
        ),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.CheckConstraint("quantity > 0", name="allocation_quantity"),
    )
    op.create_index("ix_stock_allocations_variant_id", "stock_allocations", ["variant_id"])


def downgrade():
    op.execute("""
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM checkout_quotes) THEN
                RAISE EXCEPTION 'Cannot downgrade catalog after checkout quotes have been issued';
            END IF;
        END $$;
    """)
    op.drop_table("stock_allocations")
    op.drop_table("stock_reservations")
    op.drop_table("checkout_quotes")
