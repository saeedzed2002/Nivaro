"""Commit-visible generation for public catalog list and detail keys."""

import sqlalchemy as sa
from alembic import op

revision = "0006_public_cache"
down_revision = "0005_product_media"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "public_cache_generation",
        sa.Column("id", sa.SmallInteger(), primary_key=True, autoincrement=False),
        sa.Column("token", sa.Uuid(), nullable=False),
        sa.CheckConstraint("id = 1", name="public_cache_singleton"),
    )
    op.execute("INSERT INTO public_cache_generation VALUES (1, gen_random_uuid())")
    op.execute("""
        CREATE FUNCTION advance_public_cache() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            UPDATE public_cache_generation SET token = gen_random_uuid() WHERE id = 1;
            RETURN NULL;
        END $$
    """)
    # The generation and source rows commit together. A slow reader can populate
    # only its old namespace. Expiry collects unreachable keys without a Redis write.
    for table in ("categories", "products", "variants", "market_offers", "product_media_slots"):
        op.execute(
            f"CREATE TRIGGER invalidate_public_catalog AFTER INSERT OR UPDATE OR DELETE OR TRUNCATE ON {table} FOR EACH STATEMENT EXECUTE FUNCTION advance_public_cache()"
        )


def downgrade():
    for table in ("categories", "products", "variants", "market_offers", "product_media_slots"):
        op.execute(f"DROP TRIGGER invalidate_public_catalog ON {table}")
    op.execute("DROP FUNCTION advance_public_cache()")
    op.drop_table("public_cache_generation")
