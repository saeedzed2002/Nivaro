"""Index the staff operations list by its stable sort keys."""

from alembic import op

revision = "0004_payment_operations"
down_revision = "0003_payment_delivery"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index("ix_payment_attempts_created", "payment_attempts", ["created_at", "id"])


def downgrade() -> None:
    op.drop_index("ix_payment_attempts_created", table_name="payment_attempts")
