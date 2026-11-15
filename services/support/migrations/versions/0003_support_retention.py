"""Index closed conversations by their retention cutoff."""

import sqlalchemy as sa
from alembic import op

revision = "0003_support_retention"
down_revision = "0002_support_read_cursors"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "ix_support_retention",
        "conversations",
        ["closed_at", "id"],
        postgresql_where=sa.text("status = 'closed'"),
    )


def downgrade() -> None:
    op.drop_index("ix_support_retention", table_name="conversations")
