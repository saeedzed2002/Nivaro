"""Add product edit revisions and atomic, append-only administration audit records."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql as pg

revision = "0003_admin_mutations"
down_revision = "0002_revision_guards"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "products", sa.Column("version", sa.Integer(), nullable=False, server_default="1")
    )
    op.create_check_constraint("product_version", "products", "version > 0")
    op.create_table(
        "catalog_audit_entries",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "product_id",
            sa.Uuid(),
            sa.ForeignKey("products.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("actor_id", sa.Uuid(), nullable=False),
        sa.Column("action", sa.String(60), nullable=False),
        sa.Column("target_id", sa.Uuid(), nullable=False),
        sa.Column("before", pg.JSONB(), nullable=False),
        sa.Column("after", pg.JSONB(), nullable=False),
        sa.Column("reason", sa.String(500), nullable=False),
        sa.Column("request_id", sa.String(64), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_index(
        "ix_catalog_audit_product_created",
        "catalog_audit_entries",
        ["product_id", "created_at", "id"],
    )
    op.execute("""
      CREATE FUNCTION guard_catalog_audit() RETURNS trigger LANGUAGE plpgsql AS $$
      BEGIN
        RAISE EXCEPTION 'Catalog audit entries are append only' USING ERRCODE = '23514';
      END $$;
      CREATE TRIGGER catalog_audit_immutable BEFORE UPDATE OR DELETE ON catalog_audit_entries
      FOR EACH ROW EXECUTE FUNCTION guard_catalog_audit();
    """)


def downgrade():
    raise RuntimeError("Forward-only: preserve catalog revisions and audit history")
