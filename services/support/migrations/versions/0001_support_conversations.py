"""Create private conversations, durable messages, and assignment history."""

import sqlalchemy as sa
from alembic import op

revision = "0001_support_conversations"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "conversations",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("customer_id", sa.Uuid(), nullable=False),
        sa.Column("client_conversation_id", sa.Uuid(), nullable=False),
        sa.Column("subject", sa.String(160), nullable=False),
        sa.Column("status", sa.String(10), nullable=False, server_default="open"),
        sa.Column("assigned_agent_id", sa.Uuid()),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("last_sequence", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("closed_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint(
            "customer_id", "client_conversation_id", name="uq_support_conversation_request"
        ),
        sa.CheckConstraint(
            "status IN ('open','waiting','closed') AND (status = 'closed') = (closed_at IS NOT NULL)",
            name="support_conversation_state",
        ),
        sa.CheckConstraint(
            "version > 0 AND last_sequence >= 0", name="support_conversation_counters"
        ),
        sa.CheckConstraint("char_length(subject) BETWEEN 1 AND 160", name="support_subject_length"),
    )
    op.create_index(
        "ix_support_customer_queue", "conversations", ["customer_id", "created_at", "id"]
    )
    op.create_index(
        "ix_support_agent_queue", "conversations", ["assigned_agent_id", "created_at", "id"]
    )
    op.create_index("ix_support_queue", "conversations", ["created_at", "id"])
    op.create_table(
        "messages",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "conversation_id",
            sa.Uuid(),
            sa.ForeignKey("conversations.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("sender_id", sa.Uuid(), nullable=False),
        sa.Column("sender_kind", sa.String(10), nullable=False),
        sa.Column("client_message_id", sa.Uuid(), nullable=False),
        sa.Column("sequence", sa.BigInteger(), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint("conversation_id", "sequence", name="uq_support_message_sequence"),
        sa.UniqueConstraint(
            "conversation_id",
            "sender_kind",
            "sender_id",
            "client_message_id",
            name="uq_support_message_request",
        ),
        sa.CheckConstraint("sender_kind IN ('customer','admin')", name="support_message_sender"),
        sa.CheckConstraint(
            "sequence > 0 AND char_length(body) BETWEEN 1 AND 4000", name="support_message_content"
        ),
    )
    op.create_index("ix_support_send_rate", "messages", ["sender_id", "created_at"])
    op.create_table(
        "assignment_history",
        sa.Column(
            "conversation_id",
            sa.Uuid(),
            sa.ForeignKey("conversations.id", ondelete="RESTRICT"),
            primary_key=True,
        ),
        sa.Column("version", sa.Integer(), primary_key=True),
        sa.Column("actor_id", sa.Uuid(), nullable=False),
        sa.Column("previous_agent_id", sa.Uuid()),
        sa.Column("agent_id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_table(
        "message_outbox",
        sa.Column(
            "message_id",
            sa.Uuid(),
            sa.ForeignKey("messages.id", ondelete="RESTRICT"),
            primary_key=True,
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("published_at", sa.DateTime(timezone=True)),
    )
    op.create_index(
        "ix_support_outbox_ready",
        "message_outbox",
        ["created_at", "message_id"],
        postgresql_where=sa.text("published_at IS NULL"),
    )


def downgrade() -> None:
    raise RuntimeError("Downgrading would discard private support history")
