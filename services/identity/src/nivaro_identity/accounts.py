from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, Field
from sqlalchemy import func, select, tuple_, update
from sqlalchemy.ext.asyncio import AsyncSession

from nivaro_identity.api.schemas import Input
from nivaro_identity.domain.errors import IdentityError
from nivaro_identity.domain.security import Role, StaffRole
from nivaro_identity.infrastructure.models import Administrator, Audit, Session, User, now

AccountKind = Literal["customer", "staff"]
ExpectedVersion = Annotated[int, Field(strict=True, ge=1, le=2147483647)]


class AccountSummary(BaseModel):
    id: UUID
    name: str
    phone: str
    staff_email: str | None
    role: Role
    disabled: bool
    version: int
    created_at: datetime


class AccountPage(BaseModel):
    accounts: list[AccountSummary]
    next_before: UUID | None


class StatusChange(Input):
    disabled: Annotated[bool, Field(strict=True)]
    expected_version: ExpectedVersion


class RoleChange(Input):
    role: StaffRole
    expected_version: ExpectedVersion


class AccountAudit(BaseModel):
    id: UUID
    target_id: UUID | None
    actor_id: UUID | None
    event: str
    previous_role: Role | None
    new_role: Role | None
    previous_disabled: bool | None
    new_disabled: bool | None
    created_at: datetime


class AccountAuditPage(BaseModel):
    events: list[AccountAudit]
    next_before: UUID | None


async def lock_account_changes(db: AsyncSession) -> None:
    # Shared with the operator CLI so at least one active super administrator survives.
    await db.execute(select(func.pg_advisory_xact_lock(731903)))


def summary(user: User, staff_email: str | None, role: str | None) -> AccountSummary:
    return AccountSummary.model_validate(
        {
            "id": user.id,
            "name": user.name,
            "phone": user.phone,
            "staff_email": staff_email,
            "role": role or "customer",
            "disabled": user.disabled,
            "version": user.account_version,
            "created_at": user.created_at,
        }
    )


async def list_accounts(
    db: AsyncSession,
    kind: AccountKind | None,
    disabled: bool | None,
    before: UUID | None,
    limit: int,
) -> AccountPage:
    query = select(User, Administrator.email, Administrator.role).outerjoin(
        Administrator, Administrator.user_id == User.id
    )
    if kind == "staff":
        query = query.where(Administrator.user_id.is_not(None))
    elif kind == "customer":
        query = query.where(Administrator.user_id.is_(None))
    if disabled is not None:
        query = query.where(User.disabled == disabled)
    if before is not None:
        boundary = await db.get(User, before)
        if boundary is None:
            raise IdentityError("account.not_found", 404)
        query = query.where(tuple_(User.created_at, User.id) < (boundary.created_at, boundary.id))
    rows = (
        await db.execute(query.order_by(User.created_at.desc(), User.id.desc()).limit(limit + 1))
    ).all()
    items = [summary(user, email, role) for user, email, role in rows[:limit]]
    return AccountPage(accounts=items, next_before=items[-1].id if len(rows) > limit else None)


async def list_account_audit(
    db: AsyncSession, target: UUID | None, before: UUID | None, limit: int
) -> AccountAuditPage:
    query = select(Audit)
    if target is not None:
        query = query.where(Audit.user_id == target)
    if before is not None:
        boundary = await db.get(Audit, before)
        if boundary is None or (target is not None and boundary.user_id != target):
            raise IdentityError("account.audit_cursor_not_found", 404)
        query = query.where(tuple_(Audit.created_at, Audit.id) < (boundary.created_at, boundary.id))
    rows = (
        await db.scalars(query.order_by(Audit.created_at.desc(), Audit.id.desc()).limit(limit + 1))
    ).all()
    items = [
        AccountAudit.model_validate(
            {
                "id": row.id,
                "target_id": row.user_id,
                "actor_id": row.actor_id,
                "event": row.event,
                "previous_role": row.previous_role,
                "new_role": row.new_role,
                "previous_disabled": row.previous_disabled,
                "new_disabled": row.new_disabled,
                "created_at": row.created_at,
            }
        )
        for row in rows[:limit]
    ]
    return AccountAuditPage(events=items, next_before=items[-1].id if len(rows) > limit else None)


async def target_account(
    db: AsyncSession, user_id: UUID, *, expected_version: int | None = None
) -> tuple[User, Administrator | None]:
    query = select(User).where(User.id == user_id)
    if expected_version is not None:
        query = query.with_for_update()
    user = await db.scalar(query.execution_options(populate_existing=True))
    if user is None:
        raise IdentityError("account.not_found", 404)
    if expected_version is not None and user.account_version != expected_version:
        raise IdentityError("account.version_conflict", 409)
    admin = await db.get(Administrator, user_id, populate_existing=True)
    return user, admin


async def require_another_super_admin(db: AsyncSession, user_id: UUID) -> None:
    other = await db.scalar(
        select(Administrator.user_id)
        .join(User, User.id == Administrator.user_id)
        .where(Administrator.role == "super_admin", User.disabled.is_(False), User.id != user_id)
        .limit(1)
    )
    if other is None:
        raise IdentityError("account.last_super_admin", 409)


async def change_status(
    db: AsyncSession, user: User, admin: Administrator | None, disabled: bool, actor_id: UUID | None
) -> None:
    if user.disabled == disabled:
        return
    if disabled and admin is not None and admin.role == "super_admin":
        await require_another_super_admin(db, user.id)
    previous = user.disabled
    user.disabled = disabled
    user.account_version += 1
    if disabled:
        await db.execute(
            update(Session)
            .where(
                Session.user_id == user.id,
                Session.revoked_at.is_(None),
            )
            .values(revoked_at=now())
        )
    db.add(
        Audit(
            user_id=user.id,
            actor_id=actor_id,
            event="account.disabled" if disabled else "account.enabled",
            previous_disabled=previous,
            new_disabled=disabled,
        )
    )


async def change_role(
    db: AsyncSession, user: User, admin: Administrator | None, role: StaffRole, actor_id: UUID
) -> None:
    if admin is None:
        raise IdentityError("account.not_staff", 409)
    if admin.role == role:
        return
    if admin.role == "super_admin" and not user.disabled:
        await require_another_super_admin(db, user.id)
    previous = admin.role
    admin.role = role
    user.account_version += 1
    await db.execute(
        update(Session)
        .where(
            Session.user_id == user.id,
            Session.kind == "admin",
            Session.revoked_at.is_(None),
        )
        .values(revoked_at=now())
    )
    db.add(
        Audit(
            user_id=user.id,
            actor_id=actor_id,
            event="admin.role_changed",
            previous_role=previous,
            new_role=role,
        )
    )
