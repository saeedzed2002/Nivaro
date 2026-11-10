from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def now() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"
    __table_args__ = (CheckConstraint("phone ~ '^\\+[1-9][0-9]{7,14}$'", name="phone_e164"),)
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    phone: Mapped[str] = mapped_column(String(16), unique=True)
    name: Mapped[str] = mapped_column(String(80), default="", server_default="")
    disabled: Mapped[bool] = mapped_column(default=False, server_default="false")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=now, server_default=func.now()
    )


class Administrator(Base):
    __tablename__ = "administrators"
    __table_args__ = (
        CheckConstraint(
            "role IN ('support_agent','catalog_manager','sales_manager','super_admin')",
            name="admin_role",
        ),
    )
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), primary_key=True
    )
    email: Mapped[str] = mapped_column(String(254), unique=True)
    password_hash: Mapped[str] = mapped_column(Text)
    role: Mapped[str] = mapped_column(String(32))


class Session(Base):
    __tablename__ = "sessions"
    __table_args__ = (
        CheckConstraint("kind IN ('customer','admin')", name="session_kind"),
        CheckConstraint("expires_at > created_at", name="session_expiry"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), index=True)
    family_id: Mapped[UUID] = mapped_column(unique=True, default=uuid4)
    kind: Mapped[str] = mapped_column(String(16))
    refresh_hash: Mapped[str] = mapped_column(String(64), unique=True)
    csrf_hash: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=now, server_default=func.now()
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ConsumedRefresh(Base):
    __tablename__ = "consumed_refreshes"
    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    session_id: Mapped[UUID] = mapped_column(
        ForeignKey("sessions.id", ondelete="CASCADE"), index=True
    )
    consumed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Address(Base):
    __tablename__ = "addresses"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), index=True)
    label: Mapped[str] = mapped_column(String(40))
    recipient: Mapped[str] = mapped_column(String(80))
    country: Mapped[str] = mapped_column(String(2))
    city: Mapped[str] = mapped_column(String(80))
    postal_code: Mapped[str] = mapped_column(String(20))
    street: Mapped[str] = mapped_column(String(500))
    phone: Mapped[str] = mapped_column(String(16))
    version: Mapped[int] = mapped_column(default=1, server_default="1")
    __table_args__ = (
        CheckConstraint("version > 0", name="address_version"),
        CheckConstraint("country ~ '^[A-Z]{2}$'", name="address_country"),
    )


class Audit(Base):
    __tablename__ = "audit_events"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    user_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    event: Mapped[str] = mapped_column(String(48))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=now, server_default=func.now(), index=True
    )


class AvatarSlot(Base):
    __tablename__ = "avatar_slots"
    __table_args__ = (
        UniqueConstraint("user_id", "kind", name="avatar_owner_kind"),
        CheckConstraint("kind IN ('customer','admin')", name="avatar_kind"),
        CheckConstraint("version > 0", name="avatar_version"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    kind: Mapped[str] = mapped_column(String(16))
    version: Mapped[int] = mapped_column(default=1)
    desired_job_id: Mapped[UUID | None] = mapped_column()
    active_job_id: Mapped[UUID | None] = mapped_column()


class AvatarJob(Base):
    __tablename__ = "avatar_jobs"
    __table_args__ = (
        CheckConstraint(
            "state IN ('uploaded','processing','ready','failed')", name="avatar_job_state"
        ),
        CheckConstraint("attempts BETWEEN 0 AND 3", name="avatar_job_attempts"),
        Index("ix_avatar_recovery", "state", "lease_until"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True)
    slot_id: Mapped[UUID] = mapped_column(
        ForeignKey("avatar_slots.id", ondelete="RESTRICT"), index=True
    )
    state: Mapped[str] = mapped_column(String(16), default="uploaded")
    attempts: Mapped[int] = mapped_column(default=0)
    attempt_id: Mapped[UUID | None] = mapped_column()
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_code: Mapped[str | None] = mapped_column(String(80))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AvatarDispatch(Base):
    __tablename__ = "avatar_dispatch"
    job_id: Mapped[UUID] = mapped_column(
        ForeignKey("avatar_jobs.id", ondelete="RESTRICT"), primary_key=True
    )
    available_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
    claim_id: Mapped[UUID | None] = mapped_column()
    claimed_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
