"""Persist product media slots, fenced jobs and transactional dispatch."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0005_product_media"
down_revision = "0004_category_admin"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "product_media_slots",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "product_id",
            sa.Uuid(),
            sa.ForeignKey("products.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("alt", JSONB(), nullable=False),
        sa.Column("desired_job_id", sa.Uuid()),
        sa.Column("active_job_id", sa.Uuid()),
        sa.UniqueConstraint(
            "product_id",
            "position",
            name="media_slot_position",
            deferrable=True,
            initially="DEFERRED",
        ),
        sa.CheckConstraint("position >= 0 AND position < 8", name="media_position_range"),
    )
    op.create_table(
        "product_media_jobs",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "slot_id",
            sa.Uuid(),
            sa.ForeignKey("product_media_slots.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("actor_id", sa.Uuid(), nullable=False),
        sa.Column("alt", JSONB(), nullable=False),
        sa.Column("image_kind", sa.String(20), nullable=False),
        sa.Column("state", sa.String(20), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("attempt_id", sa.Uuid()),
        sa.Column("lease_until", sa.DateTime(timezone=True)),
        sa.Column("outputs", JSONB(), nullable=False),
        sa.Column("error_code", sa.String(80)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint(
            "state IN ('uploaded','processing','ready','failed')", name="media_job_state"
        ),
        sa.CheckConstraint("attempts >= 0 AND attempts <= 3", name="media_job_attempts"),
    )
    op.create_index("ix_product_media_jobs_slot_id", "product_media_jobs", ["slot_id"])
    op.create_index("ix_media_job_recovery", "product_media_jobs", ["state", "lease_until"])
    op.create_table(
        "product_media_dispatch",
        sa.Column(
            "job_id",
            sa.Uuid(),
            sa.ForeignKey("product_media_jobs.id", ondelete="RESTRICT"),
            primary_key=True,
        ),
        sa.Column(
            "available_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("claim_id", sa.Uuid()),
        sa.Column("claimed_until", sa.DateTime(timezone=True)),
        sa.Column("confirmed_at", sa.DateTime(timezone=True)),
    )
    op.create_index(
        "ix_product_media_dispatch_available_at", "product_media_dispatch", ["available_at"]
    )


def downgrade():
    raise RuntimeError("Forward-only: preserve media history and active references")
