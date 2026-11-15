"""Store a single versioned review per buyer and product with staff decisions."""

import sqlalchemy as sa
from alembic import op

revision = "0011_product_reviews"
down_revision = "0010_purchase_entitlements"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "reviews",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "product_id",
            sa.Uuid(),
            sa.ForeignKey("products.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("customer_id", sa.Uuid(), nullable=False),
        sa.Column("rating", sa.SmallInteger(), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("status", sa.String(10), nullable=False, server_default="pending"),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint("product_id", "customer_id", name="uq_product_customer_review"),
        sa.CheckConstraint("rating BETWEEN 1 AND 5", name="review_rating_range"),
        sa.CheckConstraint("char_length(body) BETWEEN 1 AND 2000", name="review_body_length"),
        sa.CheckConstraint("status IN ('pending','approved','rejected')", name="review_status"),
        sa.CheckConstraint("version > 0", name="review_version"),
    )
    op.create_index(
        "ix_reviews_public",
        "reviews",
        ["product_id", "created_at", "id"],
        postgresql_where=sa.text("status = 'approved'"),
    )
    op.create_index("ix_reviews_moderation", "reviews", ["status", "created_at", "id"])
    op.create_table(
        "review_decisions",
        sa.Column(
            "review_id",
            sa.Uuid(),
            sa.ForeignKey("reviews.id", ondelete="RESTRICT"),
            primary_key=True,
        ),
        sa.Column("version", sa.Integer(), primary_key=True),
        sa.Column("actor_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(10), nullable=False),
        sa.Column("reason", sa.String(400), nullable=False),
        sa.Column(
            "occurred_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.CheckConstraint("status IN ('approved','rejected')", name="review_decision_status"),
        sa.CheckConstraint("char_length(reason) BETWEEN 1 AND 400", name="review_decision_reason"),
    )


def downgrade() -> None:
    raise RuntimeError("Downgrading would discard review content and moderation decisions")
