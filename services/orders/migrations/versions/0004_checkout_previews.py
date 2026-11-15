"""Persist the reviewed quote and bind it to the verified address."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0004_checkout_previews"
down_revision = "0003_reservation_inbox"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "checkout_previews",
        sa.Column(
            "operation_id",
            sa.Uuid(),
            sa.ForeignKey("checkout_operations.id", ondelete="RESTRICT"),
            primary_key=True,
        ),
        sa.Column("quote_snapshot", JSONB(), nullable=False),
        sa.Column("address_fingerprint", sa.String(64), nullable=False),
        sa.Column("totals_snapshot", JSONB(), nullable=False),
        sa.Column("confirmation", sa.String(64), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )


def downgrade() -> None:
    raise RuntimeError("Downgrading would discard checkout confirmations")
