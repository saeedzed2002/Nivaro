import json
import secrets
from time import time
from uuid import uuid4

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from jwt.algorithms import RSAAlgorithm

from nivaro_catalog.api.authorization import AuthorizationError, IdentityAuthorization
from nivaro_catalog.settings import Settings


@pytest.fixture
def material(tmp_path):
    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public = json.loads(RSAAlgorithm.to_jwk(private.public_key()))
    public.update(kid="test-key", alg="RS256", use="sig")
    path = tmp_path / "service-key"
    path.write_text(secrets.token_hex(48))
    settings = Settings(identity_service_key_file=path)
    claims = {
        "sub": str(uuid4()),
        "sid": str(uuid4()),
        "jti": str(uuid4()),
        "kind": "admin",
        "permissions": ["catalog.write"],
        "iss": settings.jwt_issuer,
        "aud": settings.jwt_audience,
        "iat": int(time()),
        "exp": int(time()) + 300,
    }
    return private, public, settings, claims


def token(material, **changes):
    private, _, _, claims = material
    return jwt.encode(
        {**claims, **changes}, private, algorithm="RS256", headers={"kid": "test-key"}
    )


def principal(material):
    claims = material[3]
    return {
        "user_id": claims["sub"],
        "session_id": claims["sid"],
        "kind": "admin",
        "permissions": claims["permissions"],
    }


async def test_public_key_is_cached_but_authoritative_session_is_never_cached(material):
    seen = []

    async def handle(request):
        seen.append(request.url.path)
        if request.url.path.endswith("jwks.json"):
            return httpx.Response(200, json={"keys": [material[1]]})
        body = json.loads(request.content)
        service = jwt.decode(
            request.headers["authorization"][7:],
            material[2].identity_service_key_file.read_text(),
            algorithms=["HS256"],
            audience="nivaro-identity-introspection",
            issuer="nivaro-catalog",
        )
        assert service["kind"] == "service" and service["exp"] - service["iat"] == 30
        assert body["access_token"] == token_value
        return httpx.Response(200, json=principal(material))

    token_value = token(material)
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handle), base_url="http://identity.test"
    ) as client:
        auth = IdentityAuthorization(material[2], client)
        for _ in range(2):
            result = await auth.check(token_value, mutating=False, origin="", csrf="")
            assert str(result.user_id) == material[3]["sub"]
    assert seen.count("/.well-known/jwks.json") == 1
    assert seen.count("/internal/v1/catalog/admin-check") == 2


@pytest.mark.parametrize(
    "changes",
    [
        {"aud": "other"},
        {"iss": "other"},
        {"kind": "customer"},
        {"exp": int(time()) - 10},
        {"sid": "not-uuid"},
        {"permissions": []},
    ],
)
async def test_invalid_browser_claims_never_reach_internal_check(material, changes):
    async def handle(request):
        assert request.url.path == "/.well-known/jwks.json"
        return httpx.Response(200, json={"keys": [material[1]]})

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handle), base_url="http://identity.test"
    ) as client:
        with pytest.raises(AuthorizationError) as exc:
            await IdentityAuthorization(material[2], client).check(
                token(material, **changes), mutating=False, origin="", csrf=""
            )
        assert exc.value.status in (401, 403)


@pytest.mark.parametrize(
    "origin,csrf", [("https://attacker.test", "present"), ("http://127.0.0.1:8080", "")]
)
async def test_mutation_origin_and_csrf_fail_before_network(material, origin, csrf):
    async def handle(request):
        pytest.fail("Invalid mutation must not reach the identity service")

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handle), base_url="http://identity.test"
    ) as client:
        with pytest.raises(AuthorizationError) as exc:
            await IdentityAuthorization(material[2], client).check(
                token(material), mutating=True, origin=origin, csrf=csrf
            )
        assert exc.value.status == 403


@pytest.mark.parametrize(
    "mode,status",
    [
        ("revoked", 401),
        ("forbidden", 403),
        ("offline", 503),
        ("invalid_body", 503),
        ("wrong_subject", 503),
        ("oversized", 503),
    ],
)
async def test_authoritative_failures_never_fall_back_to_valid_jwt(material, mode, status):
    async def handle(request):
        if request.url.path.endswith("jwks.json"):
            return httpx.Response(200, json={"keys": [material[1]]})
        if mode == "offline":
            raise httpx.ConnectError("private infrastructure failure")
        if mode in ("revoked", "forbidden"):
            return httpx.Response(status, json={"error": "private detail"})
        if mode == "invalid_body":
            return httpx.Response(200, json={"unexpected": "private detail"})
        if mode == "oversized":
            return httpx.Response(200, content=b"x" * 65537)
        return httpx.Response(200, json={**principal(material), "user_id": str(uuid4())})

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handle), base_url="http://identity.test"
    ) as client:
        with pytest.raises(AuthorizationError) as exc:
            await IdentityAuthorization(material[2], client).check(
                token(material), mutating=False, origin="", csrf=""
            )
        assert exc.value.status == status


async def test_unknown_key_refresh_has_throttle_and_expired_cache_fails_closed(material):
    calls = 0

    async def handle(request):
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(200, json={"keys": [material[1]]})
        raise httpx.ConnectError("offline")

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handle), base_url="http://identity.test"
    ) as client:
        auth = IdentityAuthorization(material[2], client)
        assert await auth._public_key("test-key")
        for _ in range(5):
            with pytest.raises(AuthorizationError) as exc:
                await auth._public_key("unknown")
            assert exc.value.status == 401
        assert calls == 1
        auth.keys_loaded_at -= 61
        with pytest.raises(AuthorizationError) as exc:
            await auth.check(token(material), mutating=False, origin="", csrf="")
        assert exc.value.status == 503


async def test_unknown_algorithm_and_missing_access_do_not_fetch_keys(material):
    async def handle(request):
        pytest.fail("Invalid algorithm must not fetch keys")

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handle), base_url="http://identity.test"
    ) as client:
        auth = IdentityAuthorization(material[2], client)
        for value in (
            "",
            "broken",
            jwt.encode(material[3], secrets.token_hex(48), algorithm="HS256"),
        ):
            with pytest.raises(AuthorizationError) as exc:
                await auth.check(value, mutating=False, origin="", csrf="")
            assert exc.value.status == 401


@pytest.mark.parametrize(
    "mode,status", [("bad_signature", 401), ("private_jwk", 503), ("bad_jwk", 503)]
)
async def test_untrusted_signature_or_key_material_fails_closed(material, mode, status):
    key = material[1]
    access = token(material)
    if mode == "bad_signature":
        other = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        access = jwt.encode(material[3], other, algorithm="RS256", headers={"kid": "test-key"})
    elif mode == "private_jwk":
        key = {
            **json.loads(RSAAlgorithm.to_jwk(material[0])),
            "kid": "test-key",
            "alg": "RS256",
            "use": "sig",
        }
    else:
        key = {**material[1], "kty": "unknown"}

    async def handle(request):
        assert request.url.path == "/.well-known/jwks.json"
        return httpx.Response(200, json={"keys": [key]})

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handle), base_url="http://identity.test"
    ) as client:
        with pytest.raises(AuthorizationError) as exc:
            await IdentityAuthorization(material[2], client).check(
                access, mutating=False, origin="", csrf=""
            )
        assert exc.value.status == status
