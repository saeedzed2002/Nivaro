"""Durable ownership, cart groups, build drafts and replay records."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0001_cart"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "owners",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("customer_id", sa.Uuid(), nullable=True),
        sa.Column("guest_digest", sa.String(length=64), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "last_active_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "(customer_id IS NOT NULL AND guest_digest IS NULL) OR (customer_id IS NULL AND guest_digest IS NOT NULL)",
            name="owner_one_identity",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("customer_id"),
        sa.UniqueConstraint("guest_digest"),
    )
    op.create_index(op.f("ix_owners_last_active_at"), "owners", ["last_active_at"], unique=False)
    op.create_table(
        "builds",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("market", sa.String(length=16), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("mode", sa.String(length=20), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.CheckConstraint(
            "(market = 'ir' AND currency = 'IRR') OR (market = 'international' AND currency = 'USD')",
            name="build_market_currency",
        ),
        sa.CheckConstraint("mode IN ('complete_build','parts_only')", name="build_mode"),
        sa.CheckConstraint("version > 0", name="build_version"),
        sa.ForeignKeyConstraint(["owner_id"], ["owners.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_builds_owner_id"), "builds", ["owner_id"], unique=False)
    op.create_table(
        "carts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("market", sa.String(length=16), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.CheckConstraint(
            "(market = 'ir' AND currency = 'IRR') OR (market = 'international' AND currency = 'USD')",
            name="cart_market_currency",
        ),
        sa.CheckConstraint("version > 0", name="cart_version"),
        sa.ForeignKeyConstraint(["owner_id"], ["owners.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("owner_id", "market", name="cart_owner_market"),
    )
    op.create_table(
        "operations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.String(length=20), nullable=False),
        sa.Column("key", sa.String(length=128), nullable=False),
        sa.Column("fingerprint", sa.String(length=64), nullable=False),
        sa.Column("result", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("kind IN ('merge','transfer','paid_cleanup')", name="operation_kind"),
        sa.ForeignKeyConstraint(["owner_id"], ["owners.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("owner_id", "kind", "key", name="operation_replay_identity"),
    )
    op.create_table(
        "build_lines",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("build_id", sa.Uuid(), nullable=False),
        sa.Column("slot_key", sa.String(length=64), nullable=False),
        sa.Column("variant_id", sa.Uuid(), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.CheckConstraint("quantity > 0", name="build_quantity"),
        sa.ForeignKeyConstraint(["build_id"], ["builds.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("build_id", "slot_key", name="build_slot"),
    )
    op.create_table(
        "cart_groups",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("cart_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("mode", sa.String(length=20), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("source_build_id", sa.Uuid(), nullable=True),
        sa.Column("source_build_version", sa.Integer(), nullable=True),
        sa.CheckConstraint("mode IN ('complete_build','parts_only')", name="group_mode"),
        sa.CheckConstraint(
            "(source_build_id IS NULL AND source_build_version IS NULL) OR (source_build_id IS NOT NULL AND source_build_version IS NOT NULL AND source_build_version > 0)",
            name="group_source_snapshot",
        ),
        sa.CheckConstraint("version > 0", name="group_version"),
        sa.ForeignKeyConstraint(["cart_id"], ["carts.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("cart_id", "id", name="group_cart_identity"),
    )
    op.create_index(op.f("ix_cart_groups_cart_id"), "cart_groups", ["cart_id"], unique=False)
    op.create_table(
        "cart_lines",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("cart_id", sa.Uuid(), nullable=False),
        sa.Column("group_id", sa.Uuid(), nullable=True),
        sa.Column("slot_key", sa.String(length=64), nullable=True),
        sa.Column("variant_id", sa.Uuid(), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.CheckConstraint(
            "(group_id IS NULL AND slot_key IS NULL) OR (group_id IS NOT NULL AND slot_key IS NOT NULL)",
            name="line_slot_scope",
        ),
        sa.CheckConstraint("quantity > 0 AND version > 0", name="line_bounds"),
        sa.ForeignKeyConstraint(
            ["cart_id", "group_id"], ["cart_groups.cart_id", "cart_groups.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["cart_id"], ["carts.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("cart_id", "group_id", "slot_key", name="cart_group_slot"),
    )
    op.create_index(op.f("ix_cart_lines_cart_id"), "cart_lines", ["cart_id"], unique=False)
    op.create_index(
        "standalone_variant",
        "cart_lines",
        ["cart_id", "variant_id"],
        unique=True,
        postgresql_where=sa.text("group_id IS NULL"),
    )


def downgrade():
    raise RuntimeError("Forward-only migration; preserve cart ownership and history")
