"""Add category revisions and append-only hierarchy audit without rewriting existing rows."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql as pg

revision = "0004_category_admin"
down_revision = "0003_admin_mutations"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "categories", sa.Column("version", sa.Integer(), nullable=False, server_default="1")
    )
    op.create_check_constraint("category_version", "categories", "version > 0")
    op.create_table(
        "category_audit_entries",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "category_id",
            sa.Uuid(),
            sa.ForeignKey("categories.id", ondelete="RESTRICT"),
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
        "ix_category_audit_created", "category_audit_entries", ["category_id", "created_at", "id"]
    )
    op.execute("""
      CREATE TRIGGER category_audit_immutable BEFORE UPDATE OR DELETE ON category_audit_entries
      FOR EACH ROW EXECUTE FUNCTION guard_catalog_audit();
    """)


def downgrade():
    raise RuntimeError("Forward-only: preserve category revisions and audit history")
