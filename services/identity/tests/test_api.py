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
    settings.catalog_service_key_file = tmp_path / "catalog-service-key"
    settings.catalog_service_key_file.write_text(secrets.token_hex(48))
    settings.cart_service_key_file = tmp_path / "cart-service-key"
    settings.cart_service_key_file.write_text(secrets.token_hex(48))
    settings.orders_client_secret_file = tmp_path / "orders-client-secret"
    settings.orders_client_secret_file.write_text(secrets.token_hex(48))
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


async def test_identity_issues_only_downscoped_orders_tokens_accepted_by_catalog(api):
    from nivaro_catalog.api.authorization import AuthorizationError, IdentityAuthorization
    from nivaro_catalog.main import app as catalog_app
    from nivaro_catalog.settings import Settings as CatalogSettings

    client, identity_app, _ = api
    path = "/internal/v1/service-tokens"
    secret = identity_app.state.orders_client_secret
    grant = {"audience": "nivaro-catalog", "scope": "catalog.quote"}
    assert (await client.post(path, json=grant)).status_code == 401
    assert (await client.post(path, json=grant, auth=("cart", secret))).status_code == 401
    for denied in ({**grant, "audience": "nivaro-browser"}, {**grant, "scope": "catalog.admin"}):
        assert (await client.post(path, json=denied, auth=("orders", secret))).status_code == 403
    issued = await client.post(path, json=grant, auth=("orders", secret))
    assert issued.status_code == 200
    auth = IdentityAuthorization(CatalogSettings(), client)
    bearer = f"Bearer {issued.json()['access_token']}"
    await auth.check_checkout(bearer, "catalog.quote")
    with pytest.raises(AuthorizationError) as wrong_scope:
        await auth.check_checkout(bearer, "catalog.reserve")
    assert wrong_scope.value.status == 403
    await login(client)
    with pytest.raises(AuthorizationError) as browser:
        await auth.check_checkout(
            f"Bearer {client.cookies['nivaro_customer_access']}", "catalog.quote"
        )
    assert browser.value.status == 401
    assert path not in identity_app.openapi()["paths"]
    assert not any(path.startswith("/internal/") for path in catalog_app.openapi()["paths"])


@pytest.mark.parametrize(
    "role, allowed, financial",
    [
        ("sales_manager", True, False),
        ("catalog_manager", False, False),
        ("super_admin", True, True),
    ],
)
async def test_orders_staff_context_checks_role_session_and_csrf(api, role, allowed, financial):
    client, app, db = api
    user_id, password = await admin_account(db, role)
    signed_in = await client.post(
        "/api/v1/admin/auth/login", json={"email": "owner@example.com", "password": password}
    )
    assert signed_in.status_code == 200, signed_in.text
    credential = ("orders", app.state.orders_client_secret)
    path = "/internal/v1/orders/staff-context"
    access = {"staff_access": client.cookies["nivaro_admin_access"]}
    del client.headers["Origin"]  # Orders authenticates directly without a browser header.
    assert (await client.post(path, json=access)).status_code == 401
    read = await client.post(path, json=access, auth=credential)
    mutation = {"origin": ORIGIN, "csrf_token": signed_in.json()["csrf_token"]}
    write = await client.post(path, json={**access, "mutation": mutation}, auth=credential)
    assert read.status_code == write.status_code == (200 if allowed else 403)
    payment_area = {**access, "area": "payments"}
    payment_read = await client.post(path, json=payment_area, auth=credential)
    assert payment_read.status_code == (200 if financial else 403)
    payment_write = await client.post(
        path, json={**payment_area, "mutation": mutation}, auth=credential
    )
    assert payment_write.status_code == 403
    if allowed:
        assert read.json() == write.json() == {"actor_id": str(user_id)}
        bad = await client.post(
            path,
            auth=credential,
            json={**access, "mutation": {**mutation, "csrf_token": "invalid"}},
        )
        assert bad.status_code == 403 and bad.json()["error"]["code"] == "csrf.invalid"
        wrong_origin = await client.post(
            path,
            auth=credential,
            json={**access, "mutation": {**mutation, "origin": "https://bad.example"}},
        )
        assert (
            wrong_origin.status_code == 403
            and wrong_origin.json()["error"]["code"] == "origin.forbidden"
        )
    client.headers["Origin"] = ORIGIN
    await login(client, SECOND)
    del client.headers["Origin"]
    customer = await client.post(
        path, json={"staff_access": client.cookies["nivaro_customer_access"]}, auth=credential
    )
    assert customer.status_code == 401


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


async def test_managed_accounts_scopes_versions_and_audit(api):
    client, _, db = api
    root_id, root_password = await admin_account(db)
    staff_password = secrets.token_urlsafe(24)
    async with db.sessions() as session, session.begin():
        staff = User(phone=SECOND)
        customer = User(phone="+12025550104")
        session.add_all([staff, customer])
        await session.flush()
        session.add(
            Administrator(
                user_id=staff.id,
                email="support@example.com",
                role="support_agent",
                password_hash=passwords.hash(staff_password),
            )
        )
    path = "/api/v1/admin/users"
    assert (await client.get(path)).status_code == 401
    await login(client, SECOND)
    customer_cookie = f"nivaro_customer_access={client.cookies['nivaro_customer_access']}"
    assert (await client.get(path, headers={"Cookie": customer_cookie})).status_code == 401
    operator = await client.post(
        "/api/v1/admin/auth/login",
        json={
            "email": "owner@example.com",
            "password": root_password,
        },
    )
    assert operator.status_code == 200
    headers = {
        "Cookie": f"nivaro_admin_access={client.cookies['nivaro_admin_access']}",
        "X-CSRF-Token": operator.json()["csrf_token"],
    }
    staff_login = await client.post(
        "/api/v1/admin/auth/login",
        json={
            "email": "support@example.com",
            "password": staff_password,
        },
    )
    assert staff_login.status_code == 200
    staff_headers = {"Cookie": f"nivaro_admin_access={client.cookies['nivaro_admin_access']}"}
    for suffix in ("", "/audit", f"/{root_id}"):
        assert (await client.get(path + suffix, headers=staff_headers)).status_code == 403
    unauthorized = await client.patch(
        f"{path}/{staff.id}/role",
        headers={**staff_headers, "X-CSRF-Token": staff_login.json()["csrf_token"]},
        json={"role": "super_admin", "expected_version": 1},
    )
    assert unauthorized.status_code == 403

    page = await client.get(path, headers=headers, params={"kind": "staff", "limit": 1})
    assert page.status_code == 200 and page.headers["cache-control"] == "no-store"
    first = page.json()
    next_page = await client.get(
        path,
        headers=headers,
        params={
            "kind": "staff",
            "limit": 1,
            "before": first["next_before"],
        },
    )
    assert {first["accounts"][0]["id"], next_page.json()["accounts"][0]["id"]} == {
        str(root_id),
        str(staff.id),
    }
    assert set(first["accounts"][0]) == {
        "id",
        "name",
        "phone",
        "staff_email",
        "role",
        "disabled",
        "version",
        "created_at",
    }
    assert next_page.json()["next_before"] is None
    customer_list = await client.get(path, headers=headers, params={"kind": "customer"})
    assert [item["id"] for item in customer_list.json()["accounts"]] == [str(customer.id)]

    target = f"{path}/{staff.id}"
    role = {"role": "catalog_manager", "expected_version": 1}
    assert (
        await client.patch(
            target + "/role",
            headers={"Cookie": headers["Cookie"]},
            json=role,
        )
    ).json()["error"]["code"] == "csrf.invalid"
    assert (
        await client.patch(
            target + "/role",
            headers={**headers, "Origin": "https://other.example"},
            json=role,
        )
    ).json()["error"]["code"] == "origin.forbidden"
    assert (
        await client.patch(
            f"{path}/{customer.id}/role",
            headers=headers,
            json=role,
        )
    ).json()["error"]["code"] == "account.not_staff"
    for suffix, body in (
        ("role", {"role": "support_agent", "expected_version": 1}),
        ("status", {"disabled": True, "expected_version": 1}),
    ):
        result = await client.patch(f"{path}/{root_id}/{suffix}", headers=headers, json=body)
        assert (
            result.status_code == 409
            and result.json()["error"]["code"] == "account.last_super_admin"
        )

    changed = await client.patch(target + "/role", headers=headers, json=role)
    assert changed.status_code == 200 and changed.json()["version"] == 2
    assert (
        await client.get("/api/v1/admin/auth/session", headers=staff_headers)
    ).status_code == 401
    assert (
        await client.get(
            "/api/v1/auth/session",
            headers={"Cookie": customer_cookie},
        )
    ).status_code == 200
    assert (
        await client.patch(
            target + "/role",
            headers=headers,
            json=role,
        )
    ).json()["error"]["code"] == "account.version_conflict"
    assert (
        await client.patch(
            target + "/role",
            headers=headers,
            json={**role, "expected_version": 2},
        )
    ).json()["version"] == 2
    assert (
        await client.patch(
            target + "/status",
            headers=headers,
            json={
                "disabled": True,
                "expected_version": 2,
            },
        )
    ).json()["version"] == 3
    assert (
        await client.get(
            "/api/v1/auth/session",
            headers={"Cookie": customer_cookie},
        )
    ).status_code == 401
    assert (
        await client.patch(
            target + "/status",
            headers=headers,
            json={
                "disabled": False,
                "expected_version": 3,
            },
        )
    ).json()["version"] == 4
    assert (
        await client.get(
            "/api/v1/auth/session",
            headers={"Cookie": customer_cookie},
        )
    ).status_code == 401

    reported = await client.get(path + "/audit", headers=headers, params={"target": str(staff.id)})
    events = reported.json()["events"]
    edits = [event for event in events if event["actor_id"] is not None]
    assert [event["event"] for event in edits] == [
        "account.enabled",
        "account.disabled",
        "admin.role_changed",
    ]
    assert {event["actor_id"] for event in edits} == {str(root_id)}
    assert (edits[-1]["previous_role"], edits[-1]["new_role"]) == (
        "support_agent",
        "catalog_manager",
    )
    assert (edits[1]["previous_disabled"], edits[1]["new_disabled"]) == (False, True)
    assert reported.status_code == 200 and "password" not in reported.text


async def test_managed_accounts_serialize_concurrent_super_admin_changes(api):
    client, _, db = api
    first_id, first_password = await admin_account(db)
    second_password = secrets.token_urlsafe(24)
    async with db.sessions() as session, session.begin():
        other = User(phone=SECOND)
        session.add(other)
        await session.flush()
        session.add(
            Administrator(
                user_id=other.id,
                email="second@example.com",
                role="super_admin",
                password_hash=passwords.hash(second_password),
            )
        )

    async def operator(email, password):
        result = await client.post(
            "/api/v1/admin/auth/login", json={"email": email, "password": password}
        )
        assert result.status_code == 200
        return {
            "Cookie": f"nivaro_admin_access={client.cookies['nivaro_admin_access']}",
            "X-CSRF-Token": result.json()["csrf_token"],
        }

    first = await operator("owner@example.com", first_password)
    second = await operator("second@example.com", second_password)
    body = {"disabled": True, "expected_version": 1}
    results = await asyncio.gather(
        client.patch(f"/api/v1/admin/users/{other.id}/status", headers=first, json=body),
        client.patch(f"/api/v1/admin/users/{first_id}/status", headers=second, json=body),
    )
    assert sorted(result.status_code for result in results) == [200, 401]
    async with db.sessions() as session:
        assert (
            await session.scalar(
                select(func.count()).select_from(User).where(User.disabled.is_(False))
            )
            == 1
        )


@pytest.mark.parametrize("change", ["logout", "role", "disable"])
async def test_catalog_bridge_uses_current_identity_state_and_session_csrf(api, change):
    from nivaro_catalog.api.authorization import AuthorizationError, IdentityAuthorization
    from nivaro_catalog.settings import Settings as CatalogSettings

    client, app, db = api
    user_id, password = await admin_account(db)
    response = await client.post(
        "/api/v1/admin/auth/login", json={"email": "owner@example.com", "password": password}
    )
    assert response.status_code == 200
    csrf = response.json()["csrf_token"]
    access = client.cookies.get("nivaro_admin_access")
    settings = CatalogSettings(
        identity_service_key_file=app.state.settings.catalog_service_key_file
    )
    # Real identity ASGI/SQL/Redis, through the actual catalog authorization client.
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://identity.test"
    ) as internal:
        bridge = IdentityAuthorization(settings, internal)
        checked = await bridge.check(access, mutating=True, origin=ORIGIN, csrf=csrf)
        assert checked.user_id == user_id
        with pytest.raises(AuthorizationError) as error:
            await bridge.check(access, mutating=True, origin=ORIGIN, csrf="wrong-csrf")
        assert error.value.status == 403
        customer = await login(client)
        with pytest.raises(AuthorizationError) as error:
            await bridge.check(
                client.cookies.get("nivaro_customer_access"), mutating=False, origin="", csrf=""
            )
        assert error.value.status == 401
        if change == "logout":
            assert (
                await client.post(
                    "/api/v1/admin/auth/logout",
                    json={"all_devices": False},
                    headers={"X-CSRF-Token": csrf},
                )
            ).status_code == 200
        else:
            async with db.sessions() as session, session.begin():
                if change == "role":
                    await session.execute(
                        update(Administrator)
                        .where(Administrator.user_id == user_id)
                        .values(role="support_agent")
                    )
                else:
                    await session.execute(
                        update(User).where(User.id == user_id).values(disabled=True)
                    )
        with pytest.raises(AuthorizationError) as error:
            await bridge.check(access, mutating=False, origin="", csrf="")
        assert error.value.status == 401
        assert customer["permissions"] == []


async def test_internal_catalog_route_rejects_browser_and_unbound_service_tokens(api):
    from time import time
    from uuid import uuid4

    import jwt

    from nivaro_identity.api.internal import CatalogCheck

    client, app, db = api
    _, password = await admin_account(db)
    await client.post(
        "/api/v1/admin/auth/login", json={"email": "owner@example.com", "password": password}
    )
    access = client.cookies.get("nivaro_admin_access")
    body = CatalogCheck(access_token=access, mutating=False)
    path = "/internal/v1/catalog/admin-check"
    assert (await client.post(path, json=body.model_dump())).status_code == 401
    assert (
        await client.post(
            path, json=body.model_dump(), headers={"Authorization": f"Bearer {access}"}
        )
    ).status_code == 401
    now_value = int(time())
    claims = {
        "iss": "nivaro-catalog",
        "sub": "catalog",
        "aud": "nivaro-identity-introspection",
        "iat": now_value,
        "exp": now_value + 30,
        "jti": str(uuid4()),
        "kind": "service",
        "scope": "catalog.admin_introspect",
        "body_sha256": body.fingerprint(),
    }
    for changed in (
        {"aud": "nivaro-browser"},
        {"kind": "admin"},
        {"exp": now_value + 300},
        {"exp": now_value - 1},
        {"body_sha256": "wrong"},
    ):
        service = jwt.encode(
            {**claims, **changed}, app.state.catalog_service_key, algorithm="HS256"
        )
        assert (
            await client.post(
                path, json=body.model_dump(), headers={"Authorization": f"Bearer {service}"}
            )
        ).status_code == 401
    valid = jwt.encode(claims, app.state.catalog_service_key, algorithm="HS256")
    altered = {**body.model_dump(), "mutating": True}
    assert (
        await client.post(path, json=altered, headers={"Authorization": f"Bearer {valid}"})
    ).status_code == 401
    result = await client.post(
        path, json=body.model_dump(), headers={"Authorization": f"Bearer {valid}"}
    )
    assert result.status_code == 200
    assert set(result.json()) == {"user_id", "session_id", "kind", "permissions"}


async def test_internal_catalog_checks_fresh_permission_even_without_catalog_client(api):
    from time import time
    from uuid import uuid4

    import jwt

    from nivaro_identity.api.internal import CatalogCheck

    client, app, db = api
    await admin_account(db, role="support_agent")
    async with db.sessions() as session:
        user = await session.scalar(select(User).where(User.phone == PHONE))
        issued = await app.state.sessions.issue(session, user, "admin")
        await session.commit()
    body = CatalogCheck(access_token=issued.access, mutating=False)
    instant = int(time())
    service = jwt.encode(
        {
            "iss": "nivaro-catalog",
            "sub": "catalog",
            "aud": "nivaro-identity-introspection",
            "iat": instant,
            "exp": instant + 30,
            "jti": str(uuid4()),
            "kind": "service",
            "scope": "catalog.admin_introspect",
            "body_sha256": body.fingerprint(),
        },
        app.state.catalog_service_key,
        algorithm="HS256",
    )
    result = await client.post(
        "/internal/v1/catalog/admin-check",
        json=body.model_dump(),
        headers={"Authorization": f"Bearer {service}"},
    )
    assert result.status_code == 403


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


async def test_checkout_snapshots_require_customer_delegation_and_exact_versions(api):
    from uuid import UUID, uuid4

    from nivaro_cart.api.authorization import IdentityAuthorization
    from nivaro_cart.infrastructure.database import Database as CartDatabase
    from nivaro_cart.infrastructure.models import Cart, CartGroup, CartLine, Owner
    from nivaro_cart.main import create_app as create_cart
    from nivaro_cart.settings import Settings as CartSettings
    from nivaro_catalog.domain.checkout import CartSnapshot

    client, identity, _ = api
    first = await login(client)
    first_access = client.cookies["nivaro_customer_access"]
    address = await client.post(
        "/api/v1/me/addresses",
        json={
            "label": "Home",
            "recipient": "Test",
            "country": "IR",
            "city": "Tehran",
            "postal_code": "1234567890",
            "street": "Synthetic address",
            "phone": PHONE,
        },
        headers={"X-CSRF-Token": first["csrf_token"]},
    )
    assert address.status_code == 201
    address_route = f"/internal/v1/orders/addresses/{address.json()['id']}"
    cart_route = "/internal/v1/orders/carts/ir"
    service_route = "/internal/v1/service-tokens"
    credentials = ("orders", identity.state.orders_client_secret)

    async def grant(audience, scope, access):
        reply = await client.post(
            service_route,
            auth=credentials,
            json={"audience": audience, "scope": scope, "customer_access": access},
        )
        assert reply.status_code == 200, reply.text
        return {"Authorization": "Bearer " + reply.json()["access_token"]}

    cart_header = await grant("nivaro-cart", "cart.checkout_snapshot", first_access)
    address_header = await grant("nivaro-identity", "identity.address_snapshot", first_access)
    assert (
        await client.get(address_route, params={"version": 1}, headers=cart_header)
    ).status_code == 401
    assert (
        await client.get(address_route, params={"version": 2}, headers=address_header)
    ).status_code == 409
    owned = await client.get(address_route, params={"version": 1}, headers=address_header)
    assert owned.json() == address.json()

    cart_settings = CartSettings()
    database = CartDatabase(cart_settings)
    async with database.sessions() as db, db.begin():
        owner_id, cart_id, group_id, line_id, source_id = (uuid4() for _ in range(5))
        db.add(Owner(id=owner_id, customer_id=UUID(first["profile"]["id"])))
        await db.flush()
        db.add(Cart(id=cart_id, owner_id=owner_id, market="ir", currency="IRR", version=3))
        await db.flush()
        db.add(
            CartGroup(
                id=group_id,
                cart_id=cart_id,
                name="Synthetic PC",
                mode="parts_only",
                version=2,
                source_build_id=source_id,
                source_build_version=5,
            )
        )
        await db.flush()
        db.add(
            CartLine(
                id=line_id,
                cart_id=cart_id,
                group_id=group_id,
                slot_key="cpu",
                variant_id=uuid4(),
                quantity=1,
                version=2,
            )
        )

    cart = create_cart(cart_settings)
    cart.state.database = database
    cart.state.authorization = IdentityAuthorization(cart_settings, client)
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=cart),
            base_url="http://cart.test",
        ) as cart_api:
            wrong_scope = await cart_api.get(
                cart_route, params={"version": 3}, headers=address_header
            )
            assert wrong_scope.status_code == 401
            stale = await cart_api.get(cart_route, params={"version": 2}, headers=cart_header)
            assert stale.status_code == 409 and stale.json()["error"]["current_version"] == 3
            current = await cart_api.get(cart_route, params={"version": 3}, headers=cart_header)
            snapshot = CartSnapshot.model_validate(current.json())
            assert snapshot.lines[0].id == line_id and snapshot.lines[0].version == 2
            assert (
                snapshot.groups[0].id == group_id
                and snapshot.groups[0].source_build_id == source_id
            )

            await login(client, SECOND)
            second_access = client.cookies["nivaro_customer_access"]
            cart_as_other = await grant("nivaro-cart", "cart.checkout_snapshot", second_access)
            address_as_other = await grant(
                "nivaro-identity", "identity.address_snapshot", second_access
            )
            assert (
                await cart_api.get(cart_route, params={"version": 3}, headers=cart_as_other)
            ).status_code == 404
            assert (
                await client.get(address_route, params={"version": 1}, headers=address_as_other)
            ).status_code == 404
            assert cart_route.replace("/ir", "/{market}") not in cart.openapi()["paths"]
    finally:
        await database.engine.dispose()


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


async def test_private_avatar_lifecycle_and_scope(api, tmp_path):
    from uuid import UUID

    from nivaro_identity.infrastructure.avatar_storage import MediaStorage
    from nivaro_identity.infrastructure.avatars import claim_job, finish_job

    client, app, db = api
    settings = app.state.settings
    settings.media_private_root = tmp_path / "private"
    settings.media_output_root = tmp_path / "outputs"
    storage = MediaStorage(settings.media_private_root, settings.media_output_root)
    _, password = await admin_account(db, role="support_agent")
    customer = await login(client)
    path = "/api/v1/me/avatar"
    staff = "/api/v1/admin/me/avatar"
    headers = {"X-CSRF-Token": customer["csrf_token"]}
    assert (await client.get(staff)).status_code == 401
    assert (await client.get(path)).json()["version"] == 0
    assert (await client.put(path, params={"version": 0}, content=b"sample")).status_code == 403
    queued = await client.put(path, params={"version": 0}, headers=headers, content=b"sample")
    assert queued.status_code == 202, queued.text
    first = UUID(queued.json()["candidate"])
    async with db.sessions() as session, session.begin():
        attempt = await claim_job(session, first)
        assert attempt is not None
        storage.write_outputs(attempt, {128: b"small", 256: b"large"})
        assert await finish_job(session, first, attempt)
    image = f"{path}/{first}/128"
    delivered = await client.get(image)
    assert delivered.content == b"small"
    assert "no-store" in delivered.headers["cache-control"]
    assert (await client.get(f"{path}/{first}/512")).status_code == 404
    assert (await client.delete(path, params={"version": 1}, headers=headers)).status_code == 409
    admin = await client.post(
        "/api/v1/admin/auth/login", json={"email": "owner@example.com", "password": password}
    )
    assert admin.status_code == 200
    assert (await client.get(staff)).json()["active"] is None
    assert (await client.get(f"{staff}/{first}/128")).status_code == 404
    assert (await client.get("/api/v1/admin/me")).json()["role"] == "support_agent"
    rejected = await client.put(path, params={"version": 2}, headers=headers, content=b"invalid")
    async with db.sessions() as session, session.begin():
        job_id = UUID(rejected.json()["candidate"])
        attempt = await claim_job(session, job_id)
        assert not await finish_job(session, job_id, attempt, error_code="invalid_image")
    state = (await client.get(path)).json()
    assert state["state"] == "failed" and state["active"] == str(first)
    pending = await client.put(
        path, params={"version": state["version"]}, headers=headers, content=b"replacement"
    )
    job_id = UUID(pending.json()["candidate"])
    async with db.sessions() as session, session.begin():
        attempt = await claim_job(session, job_id)
    removed = await client.delete(
        path, params={"version": pending.json()["version"]}, headers=headers
    )
    assert removed.status_code == 200 and removed.json()["active"] is None
    async with db.sessions() as session, session.begin():
        assert not await finish_job(session, job_id, attempt)
    assert (await client.get(image)).status_code == 404


@pytest.mark.parametrize("change", ["logout", "disable"])
async def test_cart_bridge_checks_customer_scope_revocation_and_csrf(api, change):
    from nivaro_cart.api.authorization import AuthorizationError, IdentityAuthorization
    from nivaro_cart.settings import Settings as CartSettings

    client, app, db = api
    user_id, password = await admin_account(db)
    customer = await login(client)
    access = client.cookies.get("nivaro_customer_access")
    await client.post(
        "/api/v1/admin/auth/login", json={"email": "owner@example.com", "password": password}
    )
    settings = CartSettings(identity_service_key_file=app.state.settings.cart_service_key_file)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://identity.test"
    ) as internal:
        bridge = IdentityAuthorization(settings, internal)
        principal = await bridge.check(
            access, mutating=True, origin=ORIGIN, csrf=customer["csrf_token"]
        )
        assert principal.user_id == user_id
        assert principal.kind == "customer" and principal.permissions == []
        for origin_value, csrf in (
            (ORIGIN, "wrong"),
            ("https://attacker.invalid", customer["csrf_token"]),
        ):
            with pytest.raises(AuthorizationError) as error:
                await bridge.check(access, mutating=True, origin=origin_value, csrf=csrf)
            assert error.value.status == 403
        with pytest.raises(AuthorizationError) as error:
            await bridge.check(
                client.cookies.get("nivaro_admin_access"), mutating=False, origin="", csrf=""
            )
        assert error.value.status == 401
        if change == "logout":
            assert (
                await client.post(
                    "/api/v1/auth/logout",
                    json={"all_devices": False},
                    headers={"X-CSRF-Token": customer["csrf_token"]},
                )
            ).status_code == 200
        else:
            async with db.sessions.begin() as session:
                await session.execute(update(User).where(User.id == user_id).values(disabled=True))
        with pytest.raises(AuthorizationError) as error:
            await bridge.check(access, mutating=False, origin="", csrf="")
        assert error.value.status == 401


async def test_cart_service_token_is_separate_bounded_and_request_bound(api):
    from time import time
    from uuid import uuid4

    import jwt

    from nivaro_identity.api.internal import CartCheck

    client, app, _ = api
    customer = await login(client)
    access = client.cookies.get("nivaro_customer_access")
    body = CartCheck(access_token=access, mutating=False)
    path = "/internal/v1/cart/customer-check"
    instant = int(time())
    claims = {
        "iss": "nivaro-cart",
        "sub": "cart",
        "aud": "nivaro-identity-introspection",
        "iat": instant,
        "exp": instant + 30,
        "jti": str(uuid4()),
        "kind": "service",
        "scope": "cart.customer_introspect",
        "body_sha256": body.fingerprint(),
    }
    assert (await client.post(path, json=body.model_dump())).status_code == 401
    assert (
        await client.post(
            path, json=body.model_dump(), headers={"Authorization": f"Bearer {access}"}
        )
    ).status_code == 401
    for changed in (
        {"iss": "nivaro-catalog", "sub": "catalog", "scope": "catalog.admin_introspect"},
        {"aud": "nivaro-browser"},
        {"kind": "customer"},
        {"exp": instant + 300},
        {"exp": instant - 1},
        {"jti": "invalid"},
        {"body_sha256": "wrong"},
    ):
        token = jwt.encode({**claims, **changed}, app.state.cart_service_key, algorithm="HS256")
        assert (
            await client.post(
                path, json=body.model_dump(), headers={"Authorization": f"Bearer {token}"}
            )
        ).status_code == 401
    wrong_key = jwt.encode(claims, app.state.catalog_service_key, algorithm="HS256")
    assert (
        await client.post(
            path, json=body.model_dump(), headers={"Authorization": f"Bearer {wrong_key}"}
        )
    ).status_code == 401
    valid = jwt.encode(claims, app.state.cart_service_key, algorithm="HS256")
    headers = {"Authorization": f"Bearer {valid}"}
    assert (
        await client.post(path, json={**body.model_dump(), "mutating": True}, headers=headers)
    ).status_code == 401
    assert (
        await client.post(
            "/internal/v1/catalog/admin-check", json=body.model_dump(), headers=headers
        )
    ).status_code == 401
    result = await client.post(path, json=body.model_dump(), headers=headers)
    assert result.status_code == 200 and result.json()["kind"] == "customer"
    for origin_value, csrf, status in (
        (ORIGIN, "wrong", 403),
        ("https://attacker.invalid", customer["csrf_token"], 403),
        (ORIGIN, customer["csrf_token"], 200),
    ):
        mutation = CartCheck(
            access_token=access, mutating=True, origin=origin_value, csrf_token=csrf
        )
        signed = jwt.encode(
            {**claims, "body_sha256": mutation.fingerprint()},
            app.state.cart_service_key,
            algorithm="HS256",
        )
        assert (
            await client.post(
                path, json=mutation.model_dump(), headers={"Authorization": f"Bearer {signed}"}
            )
        ).status_code == status
    app.state.cart_service_key = None
    assert (await client.post(path, json=body.model_dump(), headers=headers)).status_code == 503


async def test_real_customer_and_guest_carts_stay_private_across_login_logout(api):
    from uuid import uuid4

    from nivaro_cart.api.authorization import IdentityAuthorization
    from nivaro_cart.infrastructure.catalog import Offer, Summary
    from nivaro_cart.main import create_app as create_cart_app
    from nivaro_cart.settings import Settings as CartSettings

    _, identity, _ = api
    settings = CartSettings(
        environment="test", identity_service_key_file=identity.state.settings.cart_service_key_file
    )
    assert settings.db_host.startswith("nivaro-identity-pg-")
    cart = create_cart_app(settings)
    async with (
        LifespanManager(cart),
        httpx.AsyncClient(
            transport=httpx.ASGITransport(app=identity), base_url="http://identity.test"
        ) as internal,
    ):
        cart.state.authorization = IdentityAuthorization(settings, internal)

        class SyntheticCatalog:
            async def summaries(self, ids, market):
                return {
                    key: Summary(
                        variant_id=key,
                        product_id=key,
                        name="Synthetic fixture",
                        sku="TEST",
                        slug="test-only",
                        image="/test.webp",
                        image_kind="illustration",
                        available_quantity=20,
                        offer=Offer(
                            market=market,
                            currency="IRR" if market == "ir" else "USD",
                            amount_minor=12340,
                            price_version=1,
                            available_for_sale=True,
                            reference_only=False,
                        ),
                    )
                    for key in ids
                }

        cart.state.catalog = SyntheticCatalog()
        cart_transport, identity_transport = (
            httpx.ASGITransport(app=cart),
            httpx.ASGITransport(app=identity),
        )

        class Router(httpx.AsyncBaseTransport):
            async def handle_async_request(self, request):
                target = (
                    cart_transport
                    if request.url.path.startswith("/api/v1/cart")
                    else identity_transport
                )
                return await target.handle_async_request(request)

        async with httpx.AsyncClient(
            transport=Router(), base_url=ORIGIN, headers={"Origin": ORIGIN}
        ) as browser:
            started = await browser.post("/api/v1/cart/session", headers={"X-CSRF-Request": "1"})
            assert started.status_code == 200
            guest = (await browser.get("/api/v1/cart")).json()
            variant_id = str(uuid4())
            added = await browser.post(
                "/api/v1/cart/items",
                json={
                    "market": "ir",
                    "expected_version": guest["version"],
                    "variant_id": variant_id,
                    "quantity": 1,
                },
                headers={"X-CSRF-Token": started.json()["csrf_token"]},
            )
            assert added.status_code == 201
            customer = await login(browser)
            own = (await browser.get("/api/v1/cart")).json()
            assert own["owner_scope"] == "customer" and own["id"] != guest["id"]
            body = {
                "market": "ir",
                "expected_version": 1,
                "variant_id": variant_id,
                "quantity": 2,
            }
            assert (
                await browser.post(
                    "/api/v1/cart/items", json=body, headers={"X-CSRF-Token": "wrong"}
                )
            ).status_code == 403
            assert (
                await browser.post(
                    "/api/v1/cart/items",
                    json=body,
                    headers={"X-CSRF-Token": customer["csrf_token"]},
                )
            ).status_code == 201
            source = (await browser.get("/api/v1/cart/merge", params={"market": "ir"})).json()
            merge = {
                "market": "ir",
                "guest_cart_id": source["cart_id"],
                "expected_guest_version": source["version"],
                "expected_version": 2,
            }
            headers = {"Idempotency-Key": "login-merge", "X-CSRF-Token": customer["csrf_token"]}
            forbidden = await browser.post(
                "/api/v1/cart/merge", json=merge, headers={**headers, "X-CSRF-Token": "wrong"}
            )
            assert forbidden.status_code == 403
            merged = await browser.post("/api/v1/cart/merge", json=merge, headers=headers)
            assert merged.status_code == 200 and merged.json()["combined_lines"] == 1
            assert (
                await browser.post("/api/v1/cart/merge", json=merge, headers=headers)
            ).json() == merged.json()
            lines = (await browser.get("/api/v1/cart")).json()["lines"]
            assert len(lines) == 1 and lines[0]["quantity"] == 3
            old_access = browser.cookies.get("nivaro_customer_access")
            assert (
                await browser.post(
                    "/api/v1/auth/logout",
                    json={"all_devices": False},
                    headers={"X-CSRF-Token": customer["csrf_token"]},
                )
            ).status_code == 200
            anonymous = (await browser.get("/api/v1/cart")).json()
            assert anonymous["id"] == guest["id"] and anonymous["lines"] == []
            # Even with a valid guest cookie, a revoked customer cookie fails closed.
            assert (
                await browser.get(
                    "/api/v1/cart",
                    headers={
                        "Cookie": f"nivaro_customer_access={old_access}; nivaro_guest_cart={browser.cookies.get('nivaro_guest_cart')}"
                    },
                )
            ).status_code == 401
            await login(browser, SECOND)
            other = (await browser.get("/api/v1/cart")).json()
            assert other["id"] not in (own["id"], guest["id"]) and other["lines"] == []
