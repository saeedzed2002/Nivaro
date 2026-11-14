"""Keep transferred workload intent with the configuration group."""

import sqlalchemy as sa
from alembic import op

revision = "0006_group_intent"
down_revision = "0005_build_intent"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "cart_groups",
        sa.Column(
            "requires_dedicated_gpu", sa.Boolean(), server_default=sa.false(), nullable=False
        ),
    )


def downgrade():
    raise RuntimeError("Forward-only migration; preserve group workload intent")
