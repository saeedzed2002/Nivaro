"""Version administrative account changes and attribute audit events."""

import sqlalchemy as sa
from alembic import op

revision = "0003_identity_account_management"
down_revision = "0002_identity_avatars"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users", sa.Column("account_version", sa.Integer(), nullable=False, server_default="1")
    )
    op.create_check_constraint("identity_account_version", "users", "account_version > 0")
    op.create_index("ix_identity_users_created", "users", ["created_at", "id"])
    op.add_column(
        "audit_events",
        sa.Column("actor_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="SET NULL")),
    )
    for column in ("previous_role", "new_role"):
        op.add_column("audit_events", sa.Column(column, sa.String(32)))
    for column in ("previous_disabled", "new_disabled"):
        op.add_column("audit_events", sa.Column(column, sa.Boolean()))
    op.create_index(
        "ix_identity_audit_target_created", "audit_events", ["user_id", "created_at", "id"]
    )


def downgrade() -> None:
    raise RuntimeError("Downgrading would discard administrative account audit history")
