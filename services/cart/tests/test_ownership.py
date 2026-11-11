import hashlib
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import httpx
import pytest
from asgi_lifespan import LifespanManager
from sqlalchemy import func, select, update

from nivaro_cart.api.authorization import CustomerPrincipal
from nivaro_cart.domain.errors import AuthorizationError
from nivaro_cart.domain.ownership import GUEST_COOKIE, guest_owner, issue_guest
from nivaro_cart.infrastructure.models import Cart, CartLine, Owner
from nivaro_cart.main import create_app
from nivaro_cart.settings import Settings

ORIGIN = "http://127.0.0.1:8080"
HEADERS = {"Origin": ORIGIN, "X-CSRF-Request": "1"}


@pytest.fixture
async def api(database):
    app = create_app(Settings(environment="test"))
    async with (
        LifespanManager(app),
        httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=ORIGIN) as client,
    ):
        yield client, app


async def test_guest_bootstrap_hashes_cookie_keeps_csrf_and_separates_markets(api, database):
    client, app = api
    assert (await client.get("/api/v1/cart")).status_code == 401
    for headers in (
        {},
        {"Origin": ORIGIN},
        {**HEADERS, "Origin": "https://attacker.invalid"},
        {**HEADERS, "Sec-Fetch-Site": "cross-site"},
    ):
        assert (await client.post("/api/v1/cart/session", headers=headers)).status_code == 403
    started = await client.post("/api/v1/cart/session", headers=HEADERS)
    assert started.status_code == 200 and started.headers["cache-control"] == "no-store"
    raw = client.cookies.get(GUEST_COOKIE)
    csrf = started.json()["csrf_token"]
    assert len(raw) == 43 and raw != csrf
    assert (
        "HttpOnly" in started.headers["set-cookie"]
        and "SameSite=lax" in started.headers["set-cookie"]
    )
    async with database.sessions() as db:
        owner = await db.scalar(
            select(Owner).where(Owner.guest_digest == hashlib.sha256(raw.encode()).hexdigest())
        )
        assert owner and owner.guest_digest != raw and owner.guest_csrf == csrf
    assert (await client.get("/api/v1/cart/session")).status_code == 403
    assert (await client.get("/api/v1/cart/session", headers={"X-CSRF-Request": "1"})).json()[
        "csrf_token"
    ] == csrf
    assert (await client.post("/api/v1/cart/session", headers=HEADERS)).json()["csrf_token"] == csrf
    ir = (await client.get("/api/v1/cart?market=ir")).json()
    international = (await client.get("/api/v1/cart?market=international")).json()
    assert ir["id"] != international["id"]
    assert ir["currency"] == "IRR" and international["currency"] == "USD"
    assert ir["lines"] == [] and ir["owner_scope"] == "guest"
    assert (await client.get("/api/v1/cart?market=ir")).json()["id"] == ir["id"]
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=ORIGIN) as other:
        await other.post("/api/v1/cart/session", headers=HEADERS)
        assert (await other.get(f"/api/v1/cart?cart_id={ir['id']}")).json()["id"] != ir["id"]


async def test_guest_expiry_and_wrong_csrf_do_not_refresh_or_delete_source(database):
    async with database.sessions.begin() as db:
        issued = await issue_guest(db)
        owner_id, raw, csrf = issued.owner.id, issued.cookie, issued.owner.guest_csrf
    with pytest.raises(AuthorizationError) as error:
        async with database.sessions.begin() as db:
            await guest_owner(db, raw, csrf="x" * 43)
    assert error.value.status == 403
    async with database.sessions.begin() as db:
        assert (await guest_owner(db, raw, csrf=csrf)).id == owner_id
        old = datetime.now(UTC) - timedelta(days=31)
        await db.execute(update(Owner).where(Owner.id == owner_id).values(last_active_at=old))
    with pytest.raises(AuthorizationError) as error:
        async with database.sessions.begin() as db:
            await guest_owner(db, raw)
    assert error.value.code == "guest.expired"
    async with database.sessions() as db:
        owner = await db.get(Owner, owner_id)
        assert owner.last_active_at == old and owner.guest_csrf == csrf


@pytest.mark.parametrize("raw", ["", "../bad", "a" * 8192, "x" * 43])
async def test_guest_cookie_cannot_be_an_arbitrary_owner_identifier(database, raw):
    async with database.sessions.begin() as db:
        with pytest.raises(AuthorizationError) as error:
            await guest_owner(db, raw)
        assert error.value.status == 401


async def test_account_logout_and_second_customer_never_reuse_private_cart(api, database):
    client, app = api
    first_user, second_user = uuid4(), uuid4()

    class VerifiedIdentity:
        # Route ownership test double; real signatures/revocation/CSRF are covered
        # by the identity suite using the actual cart authorization client.
        async def check(self, access, **kwargs):
            if access == "unavailable":
                raise AuthorizationError("auth.unavailable", 503)
            if access not in ("first", "second"):
                raise AuthorizationError("auth.required", 401)
            return CustomerPrincipal(
                user_id=first_user if access == "first" else second_user,
                session_id=uuid4(),
                kind="customer",
                permissions=[],
            )

    app.state.authorization = VerifiedIdentity()
    await client.post("/api/v1/cart/session", headers=HEADERS)
    guest_cart = (await client.get("/api/v1/cart")).json()
    client.cookies.set("nivaro_customer_access", "first")
    first_cart = (await client.get("/api/v1/cart")).json()
    assert first_cart["owner_scope"] == "customer" and first_cart["id"] != guest_cart["id"]
    async with database.sessions.begin() as db:
        db.add(CartLine(cart_id=UUID(first_cart["id"]), variant_id=uuid4(), quantity=3))
    assert (await client.get("/api/v1/cart")).json()["lines"][0]["quantity"] == 3
    for invalid, status in (("expired", 401), ("unavailable", 503), ("", 401)):
        client.cookies.set("nivaro_customer_access", invalid)
        result = await client.get("/api/v1/cart")
        assert result.status_code == status and "lines" not in result.json()
        assert (await client.post("/api/v1/cart/session", headers=HEADERS)).status_code == 409
    client.cookies.delete("nivaro_customer_access")
    after_logout = (await client.get("/api/v1/cart")).json()
    assert after_logout["id"] == guest_cart["id"] and after_logout["lines"] == []
    client.cookies.set("nivaro_customer_access", "second")
    second_cart = (await client.get("/api/v1/cart")).json()
    assert second_cart["id"] not in (first_cart["id"], guest_cart["id"])
    assert second_cart["lines"] == []
    client.cookies.set("nivaro_customer_access", "first")
    assert (await client.get("/api/v1/cart")).json()["id"] == first_cart["id"]
    async with database.sessions() as db:
        assert (
            await db.scalar(
                select(func.count()).select_from(Owner).where(Owner.customer_id == first_user)
            )
            == 1
        )


async def test_release_guest_cookie_requires_https_and_is_secure(database):
    with pytest.raises(ValueError):
        Settings(environment="release")
    origin = "https://shop.example.test"
    app = create_app(Settings(environment="release", allowed_origins=[origin]))
    async with (
        LifespanManager(app),
        httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=origin) as client,
    ):
        result = await client.post(
            "/api/v1/cart/session", headers={"Origin": origin, "X-CSRF-Request": "1"}
        )
        assert result.status_code == 200
        assert (
            "Secure" in result.headers["set-cookie"] and "HttpOnly" in result.headers["set-cookie"]
        )


async def test_legacy_guest_receives_csrf_without_replacing_owned_cart(api, database):
    import secrets

    client, _ = api
    raw = secrets.token_urlsafe(32)
    async with database.sessions.begin() as db:
        owner = Owner(guest_digest=hashlib.sha256(raw.encode()).hexdigest())
        db.add(owner)
        await db.flush()
        cart = Cart(owner_id=owner.id, market="ir", currency="IRR")
        db.add(cart)
        await db.flush()
        line = CartLine(cart_id=cart.id, variant_id=uuid4(), quantity=2)
        db.add(line)
    client.cookies.set(GUEST_COOKIE, raw)
    response = await client.post("/api/v1/cart/session", headers=HEADERS)
    assert response.status_code == 200 and len(response.json()["csrf_token"]) == 43
    restored = (await client.get("/api/v1/cart")).json()
    assert restored["id"] == str(cart.id)
    assert restored["lines"][0]["id"] == str(line.id) and restored["lines"][0]["quantity"] == 2
