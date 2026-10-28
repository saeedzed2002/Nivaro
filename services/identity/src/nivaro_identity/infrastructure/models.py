from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String, Text, func
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
