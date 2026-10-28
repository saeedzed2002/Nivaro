"""Real PostgreSQL/Redis API tests, restricted to helper-created disposable DBs."""

import asyncio
import os
import secrets
from datetime import timedelta
from pathlib import Path

import httpx
import pytest
from asgi_lifespan import LifespanManager
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from sqlalchemy import URL, create_engine, func, select, text, update
from sqlalchemy.exc import OperationalError

from nivaro_identity.infrastructure.database import Database
from nivaro_identity.infrastructure.models import Administrator, ConsumedRefresh, Session, User, now
from nivaro_identity.main import create_app, passwords
from nivaro_identity.settings import Settings

pytestmark = pytest.mark.skipif(
    os.getenv("IDENTITY_SERVICE_TESTS") != "1",
    reason="Dedicated service verification helper required",
)
PHONE = "+12025550100"
SECOND = "+12025550101"
ORIGIN = "http://127.0.0.1:8080"


@pytest.fixture
async def api(tmp_path):
    settings = Settings(environment="test", otp_provider="mock", mock_phones=[PHONE, SECOND])
    assert settings.db_host.startswith("nivaro-identity-pg-"), (
        "Refuse mutations outside the disposable test database"
    )
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    settings.jwt_private_key_file = tmp_path / "test-key.pem"
    settings.jwt_private_key_file.write_bytes(
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )
    settings.otp_pepper_file = tmp_path / "test-pepper"
    settings.otp_pepper_file.write_text(secrets.token_hex(48))
    db = Database(settings)
    async with db.engine.begin() as conn:
        await conn.execute(text("TRUNCATE users CASCADE"))
    app = create_app(settings)
    async with LifespanManager(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url=ORIGIN, headers={"Origin": ORIGIN}
        ) as client:
            yield client, app, db
    await db.engine.dispose()


async def login(client, phone=PHONE):
    challenge = await client.post("/api/v1/auth/otp/request", json={"phone": phone})
    assert challenge.status_code == 200, challenge.text
    value = challenge.json()
    response = await client.post(
        "/api/v1/auth/otp/verify",
        json={
            "phone": phone,
            "challenge_id": value["challenge_id"],
            "code": value["development_code"],
        },
    )
    assert response.status_code == 200, response.text
    return response.json()


async def admin_account(db, role="super_admin"):
    raw_password = secrets.token_urlsafe(24)
    async with db.sessions() as session, session.begin():
        user = User(phone=PHONE)
        session.add(user)
        await session.flush()
        session.add(
            Administrator(
                user_id=user.id,
                email="owner@example.com",
                role=role,
                password_hash=passwords.hash(raw_password),
            )
        )
        return user.id, raw_password


async def test_health_schema_and_database_isolation(api):
    client, app, db = api
    assert (await client.get("/health/ready")).status_code == 200
    async with db.sessions() as session:
        row = (
            await session.execute(
                text(
                    "SELECT rolsuper, rolcreatedb, rolcreaterole, rolreplication FROM pg_roles WHERE rolname=current_user"
                )
            )
        ).one()
        assert not any(row)
    # Both directions: even opening the other database must be denied.
    for user, database in [
        ("nivaro_catalog", "nivaro_identity"),
        ("nivaro_identity", "nivaro_catalog"),
    ]:
        secret = (
            Path(
                "/run/secrets/"
                + ("catalog_db_password" if user == "nivaro_catalog" else "identity_db_password")
            )
            .read_text()
            .strip()
        )
        engine = create_engine(
            URL.create(
                "postgresql+psycopg",
                username=user,
                password=secret,
                host=app.state.settings.db_host,
                database=database,
            )
        )
        try:
            with pytest.raises(OperationalError):
                with engine.connect() as conn:
                    conn.execute(text("SELECT 1"))
        finally:
            engine.dispose()


async def test_account_created_only_after_single_successful_verification(api):
    client, app, db = api
    challenge = (await client.post("/api/v1/auth/otp/request", json={"phone": PHONE})).json()
    async with db.sessions() as session:
        assert await session.scalar(select(func.count()).select_from(User)) == 0
    body = {
        "phone": PHONE,
        "challenge_id": challenge["challenge_id"],
        "code": challenge["development_code"],
    }
    results = await asyncio.gather(
        *(client.post("/api/v1/auth/otp/verify", json=body) for _ in range(20))
    )
    assert [result.status_code for result in results].count(200) == 1
    assert [result.status_code for result in results].count(401) == 19
    async with db.sessions() as session:
        assert await session.scalar(select(func.count()).select_from(User)) == 1
        assert await session.scalar(select(func.count()).select_from(Session)) == 1


async def test_mock_does_not_authenticate_non_allowlisted_phone(api):
    client, app, db = api
    other = "+12025550102"
    challenge = await app.state.otp.request(other, "192.0.2.1")
    result = await client.post(
        "/api/v1/auth/otp/verify",
        json={"phone": other, "challenge_id": challenge.id, "code": challenge.code},
    )
    assert result.status_code == 401
    async with db.sessions() as session:
        assert await session.scalar(select(func.count()).select_from(User)) == 0


async def test_profile_requires_origin_csrf_and_rejects_role_injection(api):
    client, _, _ = api
    session = await login(client)
    assert (await client.patch("/api/v1/me", json={"name": "Tester"})).status_code == 403
    headers = {"X-CSRF-Token": session["csrf_token"]}
    assert (
        await client.patch(
            "/api/v1/me",
            json={"name": "Tester"},
            headers=headers | {"Origin": "https://evil.example"},
        )
    ).status_code == 403
    result = await client.patch(
        "/api/v1/me", json={"name": "Tester", "role": "super_admin"}, headers=headers
    )
    assert result.status_code == 422 and "super_admin" not in result.text
    result = await client.patch("/api/v1/me", json={"name": "آزمایش"}, headers=headers)
    assert result.status_code == 200 and result.json()["name"] == "آزمایش"
    assert result.headers["cache-control"] == "no-store"
    assert (await client.get("/api/v1/admin/auth/session")).status_code == 401


async def test_cookie_scopes_refresh_race_and_late_reuse(api):
    client, app, db = api
    state = await login(client)
    raw = client.cookies.get("nivaro_customer_refresh")
    access = client.cookies.get("nivaro_customer_access")
    cookies = list(client.cookies.jar)
    assert next(c for c in cookies if c.name.endswith("refresh")).path == "/api/v1/auth/refresh"
    assert all(c.has_nonstandard_attr("HttpOnly") for c in cookies)
    headers = {"X-CSRF-Token": state["csrf_token"], "Cookie": f"nivaro_customer_refresh={raw}"}
    results = await asyncio.gather(
        *(client.post("/api/v1/auth/refresh", headers=headers) for _ in range(8))
    )
    assert sum(r.status_code == 200 for r in results) == 1
    assert sum(r.status_code == 409 for r in results) == 7
    assert all("set-cookie" not in r.headers for r in results if r.status_code == 409)
    assert (await client.get("/api/v1/me")).status_code == 200
    async with db.sessions() as session, session.begin():
        await session.execute(
            update(ConsumedRefresh).values(consumed_at=now() - timedelta(seconds=6))
        )
    assert (await client.post("/api/v1/auth/refresh", headers=headers)).status_code == 401
    # Earlier valid access JWT is rejected immediately by authoritative state.
    assert (
        await client.get("/api/v1/me", headers={"Cookie": f"nivaro_customer_access={access}"})
    ).status_code == 401


async def test_refresh_csrf_after_access_expiry_and_cross_origin_denial(api):
    client, _, _ = api
    state = await login(client)
    client.cookies.delete("nivaro_customer_access")
    assert (await client.get("/api/v1/auth/session")).status_code == 401
    route = "/api/v1/auth/refresh/csrf"
    assert (await client.get(route)).status_code == 403
    assert (
        await client.get(route, headers={"X-CSRF-Request": "1", "Origin": "https://evil.example"})
    ).status_code == 403
    csrf = await client.get(route, headers={"X-CSRF-Request": "1"})
    assert csrf.status_code == 200 and csrf.json()["csrf_token"] == state["csrf_token"]
    assert (
        await client.post(
            "/api/v1/auth/refresh", headers={"X-CSRF-Token": csrf.json()["csrf_token"]}
        )
    ).status_code == 200
    assert (await client.get("/api/v1/me")).status_code == 200


async def test_customer_admin_sessions_are_separate_for_same_person(api):
    client, _, db = api
    _, password = await admin_account(db, "support_agent")
    customer = await login(client)
    assert customer["permissions"] == []
    assert (await client.get("/api/v1/admin/auth/session")).status_code == 401
    result = await client.post(
        "/api/v1/admin/auth/login", json={"email": "owner@example.com", "password": password}
    )
    assert result.status_code == 200, result.text
    assert result.json()["profile"]["id"] == customer["profile"]["id"]
    assert result.json()["permissions"] == ["support.reply"]
    assert client.cookies.get("nivaro_customer_refresh") != client.cookies.get(
        "nivaro_admin_refresh"
    )
    assert (
        await client.post(
            "/api/v1/admin/auth/logout", json={}, headers={"X-CSRF-Token": customer["csrf_token"]}
        )
    ).status_code == 403
    result = await client.post(
        "/api/v1/auth/logout",
        json={"all_devices": True},
        headers={"X-CSRF-Token": customer["csrf_token"]},
    )
    assert result.status_code == 200
    assert (await client.get("/api/v1/admin/auth/session")).status_code == 200


async def test_admin_attempt_limits_and_generic_errors(api):
    client, _, db = api
    await admin_account(db)
    existing = await client.post(
        "/api/v1/admin/auth/login", json={"email": "owner@example.com", "password": "wrong"}
    )
    missing = await client.post(
        "/api/v1/admin/auth/login", json={"email": "missing@example.com", "password": "wrong"}
    )
    assert existing.status_code == missing.status_code == 401
    assert existing.json()["error"]["code"] == missing.json()["error"]["code"] == "login.invalid"
    for _ in range(4):
        assert (
            await client.post(
                "/api/v1/admin/auth/login", json={"email": "owner@example.com", "password": "wrong"}
            )
        ).status_code == 401
    assert (
        await client.post(
            "/api/v1/admin/auth/login", json={"email": "owner@example.com", "password": "wrong"}
        )
    ).status_code == 429


async def test_address_ownership_validation_and_stale_edits(api):
    client, _, _ = api
    first = await login(client)
    headers = {"X-CSRF-Token": first["csrf_token"]}
    body = {
        "label": "Home",
        "recipient": "Test",
        "country": "IR",
        "city": "تهران",
        "postal_code": "۱۲۳۴۵۶۷۸۹۰",
        "street": "Synthetic test address",
        "phone": PHONE,
    }
    result = await client.post("/api/v1/me/addresses", json=body, headers=headers)
    assert result.status_code == 201, result.text
    item = result.json()
    route = "/api/v1/me/addresses/" + item["id"]
    assert item["postal_code"] == "1234567890"
    assert (
        await client.put(route, json=body | {"version": 1, "label": "Updated"}, headers=headers)
    ).status_code == 200
    assert (await client.put(route, json=body | {"version": 1}, headers=headers)).status_code == 409
    assert (await client.delete(route + "?version=1", headers=headers)).status_code == 409
    second = await login(client, SECOND)
    assert (await client.get("/api/v1/me/addresses")).json() == []
    assert (
        await client.delete(route + "?version=2", headers={"X-CSRF-Token": second["csrf_token"]})
    ).status_code == 404


async def test_disabled_account_fails_closed(api):
    client, _, db = api
    state = await login(client)
    async with db.sessions() as session, session.begin():
        await session.execute(update(User).values(disabled=True))
    assert (await client.get("/api/v1/me")).status_code == 401
    assert (
        await client.post("/api/v1/auth/refresh", headers={"X-CSRF-Token": state["csrf_token"]})
    ).status_code == 401


async def test_absolute_session_expiry_and_logout_all_devices(api):
    client, app, db = api
    state = await login(client)
    old_access = client.cookies.get("nivaro_customer_access")
    async with db.sessions() as session, session.begin():
        user = await session.scalar(select(User).where(User.phone == PHONE).with_for_update())
        issued = await app.state.sessions.issue(session, user, "customer")
    assert (
        await client.post(
            "/api/v1/auth/logout",
            json={"all_devices": True},
            headers={"X-CSRF-Token": state["csrf_token"]},
        )
    ).status_code == 200
    for access in [old_access, issued.access]:
        assert (
            await client.get("/api/v1/me", headers={"Cookie": f"nivaro_customer_access={access}"})
        ).status_code == 401
    state = await login(client, SECOND)
    async with db.sessions() as session, session.begin():
        await session.execute(
            update(Session).values(
                created_at=now() - timedelta(days=31), expires_at=now() - timedelta(seconds=1)
            )
        )
    assert (await client.get("/api/v1/me")).status_code == 401
    assert (
        await client.post("/api/v1/auth/refresh", headers={"X-CSRF-Token": state["csrf_token"]})
    ).status_code == 401


async def test_operator_bootstrap_and_password_change_revoke_admin_only(api, monkeypatch):
    from nivaro_identity.manage import manage

    client, app, db = api
    customer = await login(client)
    password = secrets.token_urlsafe(24)
    answers = iter([PHONE, "owner@example.com"])
    monkeypatch.setattr("builtins.input", lambda _: next(answers))
    monkeypatch.setattr("getpass.getpass", lambda _: password)
    await manage("bootstrap-admin")
    with pytest.raises(ValueError, match="already completed"):
        await manage("bootstrap-admin")
    result = await client.post(
        "/api/v1/admin/auth/login", json={"email": "owner@example.com", "password": password}
    )
    assert result.status_code == 200
    assert result.json()["profile"]["id"] == customer["profile"]["id"]
    monkeypatch.setattr("builtins.input", lambda _: "owner@example.com")
    replacement = secrets.token_urlsafe(24)
    monkeypatch.setattr("getpass.getpass", lambda _: replacement)
    await manage("change-admin-password")
    assert (await client.get("/api/v1/admin/auth/session")).status_code == 401
    assert (await client.get("/api/v1/me")).status_code == 200
    assert (
        await client.post(
            "/api/v1/admin/auth/login", json={"email": "owner@example.com", "password": password}
        )
    ).status_code == 401
    assert (
        await client.post(
            "/api/v1/admin/auth/login", json={"email": "owner@example.com", "password": replacement}
        )
    ).status_code == 200


async def test_release_cookie_security_and_dependency_failure(api, monkeypatch):
    from redis.exceptions import ConnectionError as RedisConnectionError
    from sqlalchemy.exc import OperationalError
    from starlette.responses import Response

    from nivaro_identity.main import set_cookies

    client, app, db = api
    await login(client)
    async with db.sessions() as session, session.begin():
        user = await session.scalar(select(User).where(User.phone == PHONE).with_for_update())
        issued = await app.state.sessions.issue(session, user, "customer")
        release = Settings(environment="release", allowed_origins=["https://shop.example.com"])
        response = Response()
        set_cookies(response, issued, "customer", release)
        assert all(
            "Secure" in c and "HttpOnly" in c for c in response.headers.getlist("set-cookie")
        )

    async def redis_unavailable(*args, **kwargs):
        raise RedisConnectionError("synthetic secret must not leak")

    monkeypatch.setattr(app.state.redis, "eval", redis_unavailable)
    result = await client.post("/api/v1/auth/otp/request", json={"phone": SECOND})
    assert result.status_code == 503 and "synthetic" not in result.text
    # Existing sessions can use authoritative PostgreSQL while Redis is down.
    assert (await client.get("/api/v1/me")).status_code == 200

    async def database_unavailable(*args, **kwargs):
        raise OperationalError("synthetic private SQL", {}, Exception("secret"))

    monkeypatch.setattr(app.state.sessions, "authenticate", database_unavailable)
    result = await client.get("/api/v1/me")
    assert (
        result.status_code == 503 and "synthetic" not in result.text and "secret" not in result.text
    )


async def test_limits_private_routes_and_public_keys(api):
    client, app, _ = api
    assert (await client.post("/api/v1/auth/otp/request", content=b"x" * 20000)).status_code == 413
    assert (await client.get("/docs")).status_code == 404
    assert (await client.get("/openapi.json")).status_code == 404
    keys = (await client.get("/.well-known/jwks.json")).json()["keys"]
    assert len(keys) == 1 and "d" not in keys[0]
    await app.state.redis.aclose()
    # Availability is also covered by the real-Redis foundation test; disabling
    # delivery never produces an apparently successful send.
    app.state.settings.otp_provider = "disabled"
    assert (await client.post("/api/v1/auth/otp/request", json={"phone": PHONE})).status_code == 503
