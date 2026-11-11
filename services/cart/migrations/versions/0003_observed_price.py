"""Remember first observed line price to expose later repricing without freezing it."""

import sqlalchemy as sa
from alembic import op

revision = "0003_observed_price"
down_revision = "0002_guest_csrf"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("cart_lines", sa.Column("observed_price_minor", sa.BigInteger(), nullable=True))
    op.add_column("cart_lines", sa.Column("observed_price_version", sa.Integer(), nullable=True))
    op.create_check_constraint(
        "line_observed_price",
        "cart_lines",
        "(observed_price_minor IS NULL AND observed_price_version IS NULL) OR "
        "(observed_price_minor IS NOT NULL AND observed_price_version IS NOT NULL AND "
        "observed_price_minor > 0 AND observed_price_version > 0)",
    )


def downgrade():
    raise RuntimeError("Forward-only migration; preserve cart price history")
