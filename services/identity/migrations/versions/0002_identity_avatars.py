"""Separate avatar slots, recoverable jobs and dispatch for identity."""

import sqlalchemy as sa
from alembic import op

revision = "0002_identity_avatars"
down_revision = "0001_identity"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "avatar_slots",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
        ),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("desired_job_id", sa.Uuid()),
        sa.Column("active_job_id", sa.Uuid()),
        sa.UniqueConstraint("user_id", "kind", name="avatar_owner_kind"),
        sa.CheckConstraint("kind IN ('customer','admin')", name="avatar_kind"),
        sa.CheckConstraint("version > 0", name="avatar_version"),
    )
    op.create_table(
        "avatar_jobs",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "slot_id",
            sa.Uuid(),
            sa.ForeignKey("avatar_slots.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("state", sa.String(16), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("attempt_id", sa.Uuid()),
        sa.Column("lease_until", sa.DateTime(timezone=True)),
        sa.Column("error_code", sa.String(80)),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint(
            "state IN ('uploaded','processing','ready','failed')", name="avatar_job_state"
        ),
        sa.CheckConstraint("attempts BETWEEN 0 AND 3", name="avatar_job_attempts"),
    )
    op.create_index("ix_avatar_jobs_slot_id", "avatar_jobs", ["slot_id"])
    op.create_index("ix_avatar_recovery", "avatar_jobs", ["state", "lease_until"])
    op.create_table(
        "avatar_dispatch",
        sa.Column(
            "job_id",
            sa.Uuid(),
            sa.ForeignKey("avatar_jobs.id", ondelete="RESTRICT"),
            primary_key=True,
        ),
        sa.Column(
            "available_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("claim_id", sa.Uuid()),
        sa.Column("claimed_until", sa.DateTime(timezone=True)),
        sa.Column("confirmed_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_avatar_dispatch_available_at", "avatar_dispatch", ["available_at"])


def downgrade():
    raise RuntimeError("Forward-only migration: preserve identity media history")
