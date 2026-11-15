"""Operator-only CLI. Never seeds default passwords or exposes public signup."""

import argparse
import asyncio
import getpass
from datetime import timedelta

from email_validator import validate_email
from sqlalchemy import delete, func, select, update

from nivaro_identity.accounts import change_status, lock_account_changes
from nivaro_identity.domain.errors import IdentityError
from nivaro_identity.domain.phone import normalize_phone
from nivaro_identity.infrastructure.database import Database
from nivaro_identity.infrastructure.models import Administrator, Audit, Session, User, now
from nivaro_identity.main import passwords
from nivaro_identity.settings import Settings


def new_password() -> str:
    value = getpass.getpass("New administrator password (12-256 characters): ")
    if not 12 <= len(value) <= 256 or value != getpass.getpass("Repeat password: "):
        raise ValueError("Password length or confirmation failed")
    return passwords.hash(value)


async def manage(action: str) -> None:
    database = Database(Settings())
    try:
        async with database.sessions() as db, db.begin():
            if action == "bootstrap-admin":
                # Serialize simultaneous bootstrap attempts without a seed admin.
                await lock_account_changes(db)
                if await db.scalar(select(func.count()).select_from(Administrator)):
                    raise ValueError("Administrator bootstrap already completed")
                phone = normalize_phone(input("Owner mobile number with country code: "))
                email = validate_email(
                    input("Administrator email: ").strip(), check_deliverability=False
                ).normalized.lower()
                encoded = new_password()
                user = await db.scalar(select(User).where(User.phone == phone).with_for_update())
                if user is None:
                    user = User(phone=phone)
                    db.add(user)
                    await db.flush()
                if user.disabled:
                    raise ValueError("Account is disabled")
                db.add(
                    Administrator(
                        user_id=user.id, email=email, password_hash=encoded, role="super_admin"
                    )
                )
                db.add(Audit(user_id=user.id, event="admin.bootstrap"))
            elif action == "change-admin-password":
                email = validate_email(
                    input("Administrator email: ").strip(), check_deliverability=False
                ).normalized.lower()
                admin = await db.scalar(select(Administrator).where(Administrator.email == email))
                if admin is None:
                    raise ValueError("Administrator not found")
                await db.scalar(select(User).where(User.id == admin.user_id).with_for_update())
                admin.password_hash = new_password()
                await db.execute(
                    update(Session)
                    .where(
                        Session.user_id == admin.user_id,
                        Session.kind == "admin",
                        Session.revoked_at.is_(None),
                    )
                    .values(revoked_at=now())
                )
                db.add(Audit(user_id=admin.user_id, event="admin.password_changed"))
            elif action == "disable-user":
                phone = normalize_phone(input("Mobile number to disable: "))
                await lock_account_changes(db)
                user = await db.scalar(select(User).where(User.phone == phone).with_for_update())
                if user is None:
                    raise ValueError("Account not found")
                await change_status(db, user, await db.get(Administrator, user.id), True, None)
            elif action == "prune-expired":
                await db.execute(
                    delete(Session).where(Session.expires_at < now() - timedelta(days=7))
                )
                await db.execute(delete(Audit).where(Audit.created_at < now() - timedelta(days=90)))
        print("Identity operator command completed. No credential values were logged.")
    finally:
        await database.engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "action",
        choices=["bootstrap-admin", "change-admin-password", "disable-user", "prune-expired"],
    )
    try:
        asyncio.run(manage(parser.parse_args().action))
    except (ValueError, IdentityError) as error:
        raise SystemExit(str(error)) from None
