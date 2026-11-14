"""Allow atomic reparenting of an intact configuration group and its lines."""

from alembic import op

revision = "0004_cart_merge"
down_revision = "0003_observed_price"
branch_labels = None
depends_on = None


def upgrade():
    op.drop_constraint("cart_lines_cart_id_group_id_fkey", "cart_lines", type_="foreignkey")
    op.create_foreign_key(
        "cart_line_group_owner",
        "cart_lines",
        "cart_groups",
        ["cart_id", "group_id"],
        ["cart_id", "id"],
        ondelete="CASCADE",
        deferrable=True,
        initially="IMMEDIATE",
    )


def downgrade():
    raise RuntimeError("Forward-only migration; preserve cart merge history")
