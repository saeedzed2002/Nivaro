"""Catalog foundation: independent physical variants and market offers.

Revision ID: 0001_catalog
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql as pg

revision = "0001_catalog"
down_revision = None
branch_labels = None
depends_on = None


def timestamps():
    return [
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    ]


def upgrade():
    op.create_table(
        "categories",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("slug", sa.String(80), nullable=False, unique=True),
        sa.Column("name", pg.JSONB(), nullable=False),
        sa.Column("image", sa.String(100), nullable=False),
        sa.Column("parent_id", sa.Uuid(), sa.ForeignKey("categories.id", ondelete="RESTRICT")),
        *timestamps(),
    )
    op.create_index("ix_categories_parent_id", "categories", ["parent_id"])
    # The two-level constraint includes moves of a parent that already has children.
    op.execute("""
        CREATE FUNCTION check_category_depth() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
          IF NEW.parent_id IS NOT NULL THEN
            IF NEW.parent_id = NEW.id
              OR EXISTS (SELECT 1 FROM categories WHERE id = NEW.parent_id AND parent_id IS NOT NULL)
              OR EXISTS (SELECT 1 FROM categories WHERE parent_id = NEW.id)
            THEN RAISE EXCEPTION 'Category depth exceeds two levels' USING ERRCODE = '23514';
            END IF;
          END IF;
          RETURN NEW;
        END $$;
        CREATE TRIGGER category_depth BEFORE INSERT OR UPDATE OF parent_id ON categories
        FOR EACH ROW EXECUTE FUNCTION check_category_depth();
    """)
    op.create_table(
        "products",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("slug", sa.String(160), nullable=False, unique=True),
        sa.Column("name", sa.String(240), nullable=False),
        sa.Column("description", pg.JSONB(), nullable=False),
        sa.Column(
            "category_id",
            sa.Uuid(),
            sa.ForeignKey("categories.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("brand", sa.String(120), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("image", sa.String(100), nullable=False),
        sa.Column("image_ready", sa.Boolean(), nullable=False),
        sa.Column("image_kind", sa.String(20), nullable=False),
        sa.Column("highlights", pg.ARRAY(sa.Text()), nullable=False),
        sa.Column("search_tokens", pg.ARRAY(sa.Text()), nullable=False),
        sa.CheckConstraint("status IN ('draft','published','archived')", name="product_status"),
        *timestamps(),
    )
    op.create_index("ix_products_brand", "products", ["brand"])
    op.create_index("ix_products_status_category", "products", ["status", "category_id"])
    op.create_index(
        "ix_products_search_tokens", "products", ["search_tokens"], postgresql_using="gin"
    )
    op.create_table(
        "variants",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "product_id",
            sa.Uuid(),
            sa.ForeignKey("products.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("sku", sa.String(100), nullable=False, unique=True),
        sa.Column("packaging", pg.JSONB(), nullable=False),
        sa.Column("specifications", pg.JSONB(), nullable=False),
        sa.Column("spec_version", sa.Integer(), nullable=False),
        sa.Column("evidence", pg.JSONB(), nullable=False),
        sa.Column("stock_kind", sa.String(30), nullable=False),
        sa.Column("on_hand", sa.BigInteger(), nullable=False),
        sa.Column("reserved", sa.BigInteger(), nullable=False),
        sa.Column("stock_verified", sa.Boolean(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.CheckConstraint(
            "on_hand >= 0 AND reserved >= 0 AND reserved <= on_hand", name="variant_stock"
        ),
        sa.CheckConstraint("spec_version > 0 AND version > 0", name="variant_versions"),
        sa.CheckConstraint(
            "stock_kind IN ('component','accessory','stocked_prebuilt')", name="variant_stock_kind"
        ),
        sa.CheckConstraint(
            "(stock_kind = 'stocked_prebuilt') = (specifications->>'kind' = 'prebuilt')",
            name="prebuilt_stock_isolation",
        ),
        sa.CheckConstraint(
            "(stock_kind = 'accessory') = (specifications->>'kind' = 'peripheral')",
            name="accessory_stock_kind",
        ),
        sa.CheckConstraint(
            "jsonb_typeof(specifications) = 'object' AND specifications ? 'kind'",
            name="typed_specs_required",
        ),
        *timestamps(),
    )
    op.create_index("ix_variants_product_id", "variants", ["product_id"])
    op.create_table(
        "market_offers",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "variant_id",
            sa.Uuid(),
            sa.ForeignKey("variants.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("market", sa.String(20), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("amount_minor", sa.BigInteger(), nullable=False),
        sa.Column("price_version", sa.Integer(), nullable=False),
        sa.Column("available_for_sale", sa.Boolean(), nullable=False),
        sa.Column("reference_only", sa.Boolean(), nullable=False),
        sa.Column("source", pg.JSONB(), nullable=False),
        sa.Column("seller", sa.String(120), nullable=False),
        sa.UniqueConstraint("variant_id", "market", name="uq_variant_market"),
        sa.CheckConstraint(
            "(market = 'ir' AND currency = 'IRR') OR (market = 'international' AND currency = 'USD')",
            name="offer_market_currency",
        ),
        sa.CheckConstraint(
            "amount_minor > 0 AND amount_minor <= 9000000000000 AND (currency <> 'IRR' OR amount_minor % 10 = 0)",
            name="offer_amount",
        ),
        sa.CheckConstraint("price_version > 0", name="offer_version"),
        sa.CheckConstraint(
            "NOT (reference_only AND available_for_sale)", name="reference_not_sellable"
        ),
        *timestamps(),
    )
    op.create_index("ix_market_offers_variant_id", "market_offers", ["variant_id"])


def downgrade():
    # Never run a destructive downgrade against owner data without explicit authorization.
    op.drop_table("market_offers")
    op.drop_table("variants")
    op.drop_table("products")
    op.drop_table("categories")
    op.execute("DROP FUNCTION check_category_depth()")
