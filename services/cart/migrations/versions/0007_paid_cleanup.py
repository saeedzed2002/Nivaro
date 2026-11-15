"""Remember when a paid order encountered later cart edits."""

import sqlalchemy as sa
from alembic import op

revision = "0007_paid_cleanup"
down_revision = "0006_group_intent"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "carts",
        sa.Column(
            "paid_cleanup_needs_review", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
    )


def downgrade() -> None:
    raise RuntimeError("Downgrading would discard the paid cart review flag")
