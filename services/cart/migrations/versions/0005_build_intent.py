"""Persist the workload intent used to re-evaluate saved builds."""

import sqlalchemy as sa
from alembic import op

revision = "0005_build_intent"
down_revision = "0004_cart_merge"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "builds",
        sa.Column(
            "requires_dedicated_gpu", sa.Boolean(), server_default=sa.false(), nullable=False
        ),
    )


def downgrade():
    raise RuntimeError("Forward-only migration; preserve saved build intent")
