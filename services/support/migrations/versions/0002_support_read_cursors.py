"""Store each participant's highest read sequence."""

import sqlalchemy as sa
from alembic import op

revision = "0002_support_read_cursors"
down_revision = "0001_support_conversations"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "read_cursors",
        sa.Column(
            "conversation_id",
            sa.Uuid(),
            sa.ForeignKey("conversations.id", ondelete="RESTRICT"),
            primary_key=True,
        ),
        sa.Column("reader_kind", sa.String(10), primary_key=True),
        sa.Column("reader_id", sa.Uuid(), primary_key=True),
        sa.Column("sequence", sa.BigInteger(), nullable=False),
        sa.Column("published_sequence", sa.BigInteger(), nullable=False, server_default="0"),
        sa.CheckConstraint("reader_kind IN ('customer','admin')", name="support_cursor_reader"),
        sa.CheckConstraint(
            "sequence > 0 AND published_sequence >= 0 AND published_sequence <= sequence",
            name="support_cursor_sequences",
        ),
    )
    op.create_index(
        "ix_support_read_cursor_ready",
        "read_cursors",
        ["conversation_id", "reader_kind", "reader_id"],
        postgresql_where=sa.text("published_sequence < sequence"),
    )


def downgrade() -> None:
    raise RuntimeError("Downgrading would discard private read history")
