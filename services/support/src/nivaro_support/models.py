from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class ConversationRow(Base):
    __tablename__ = "conversations"
    __table_args__ = (
        UniqueConstraint(
            "customer_id", "client_conversation_id", name="uq_support_conversation_request"
        ),
        CheckConstraint(
            "status IN ('open','waiting','closed') AND (status = 'closed') = (closed_at IS NOT NULL)",
            name="support_conversation_state",
        ),
        CheckConstraint("version > 0 AND last_sequence >= 0", name="support_conversation_counters"),
        CheckConstraint("char_length(subject) BETWEEN 1 AND 160", name="support_subject_length"),
        Index("ix_support_customer_queue", "customer_id", "created_at", "id"),
        Index("ix_support_agent_queue", "assigned_agent_id", "created_at", "id"),
        Index("ix_support_queue", "created_at", "id"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True)
    customer_id: Mapped[UUID] = mapped_column()
    client_conversation_id: Mapped[UUID] = mapped_column()
    subject: Mapped[str] = mapped_column(String(160))
    status: Mapped[str] = mapped_column(String(10), server_default="open")
    assigned_agent_id: Mapped[UUID | None] = mapped_column()
    version: Mapped[int] = mapped_column(Integer, server_default="1")
    last_sequence: Mapped[int] = mapped_column(BigInteger, server_default="0")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class MessageRow(Base):
    __tablename__ = "messages"
    __table_args__ = (
        UniqueConstraint("conversation_id", "sequence", name="uq_support_message_sequence"),
        UniqueConstraint(
            "conversation_id",
            "sender_kind",
            "sender_id",
            "client_message_id",
            name="uq_support_message_request",
        ),
        CheckConstraint("sender_kind IN ('customer','admin')", name="support_message_sender"),
        CheckConstraint(
            "sequence > 0 AND char_length(body) BETWEEN 1 AND 4000", name="support_message_content"
        ),
        Index("ix_support_send_rate", "sender_id", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True)
    conversation_id: Mapped[UUID] = mapped_column(
        ForeignKey("conversations.id", ondelete="RESTRICT")
    )
    sender_id: Mapped[UUID] = mapped_column()
    sender_kind: Mapped[str] = mapped_column(String(10))
    client_message_id: Mapped[UUID] = mapped_column()
    sequence: Mapped[int] = mapped_column(BigInteger)
    body: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AssignmentRow(Base):
    __tablename__ = "assignment_history"

    conversation_id: Mapped[UUID] = mapped_column(
        ForeignKey("conversations.id", ondelete="RESTRICT"), primary_key=True
    )
    version: Mapped[int] = mapped_column(Integer, primary_key=True)
    actor_id: Mapped[UUID] = mapped_column()
    previous_agent_id: Mapped[UUID | None] = mapped_column()
    agent_id: Mapped[UUID] = mapped_column()
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class MessageOutboxRow(Base):
    __tablename__ = "message_outbox"
    __table_args__ = (
        Index(
            "ix_support_outbox_ready",
            "created_at",
            "message_id",
            postgresql_where=text("published_at IS NULL"),
        ),
    )

    message_id: Mapped[UUID] = mapped_column(
        ForeignKey("messages.id", ondelete="RESTRICT"), primary_key=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ReadCursorRow(Base):
    __tablename__ = "read_cursors"
    __table_args__ = (
        CheckConstraint("reader_kind IN ('customer','admin')", name="support_cursor_reader"),
        CheckConstraint(
            "sequence > 0 AND published_sequence >= 0 AND published_sequence <= sequence",
            name="support_cursor_sequences",
        ),
        Index(
            "ix_support_read_cursor_ready",
            "conversation_id",
            "reader_kind",
            "reader_id",
            postgresql_where=text("published_sequence < sequence"),
        ),
    )

    conversation_id: Mapped[UUID] = mapped_column(
        ForeignKey("conversations.id", ondelete="RESTRICT"), primary_key=True
    )
    reader_kind: Mapped[str] = mapped_column(String(10), primary_key=True)
    reader_id: Mapped[UUID] = mapped_column(primary_key=True)
    sequence: Mapped[int] = mapped_column(BigInteger)
    published_sequence: Mapped[int] = mapped_column(BigInteger, server_default="0")
