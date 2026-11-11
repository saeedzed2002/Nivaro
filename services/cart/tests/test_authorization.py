import json
import secrets
from time import time
from uuid import uuid4

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from jwt.algorithms import RSAAlgorithm

from nivaro_cart.api.authorization import IdentityAuthorization
from nivaro_cart.domain.errors import AuthorizationError
from nivaro_cart.settings import Settings


@pytest.fixture
def signed_customer(tmp_path):
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public = json.loads(RSAAlgorithm.to_jwk(key.public_key()))
    public.update(kid="test-customer", alg="RS256", use="sig")
    instant = int(time())
    user_id, session_id = str(uuid4()), str(uuid4())
    access = jwt.encode(
        {
            "sub": user_id,
            "sid": session_id,
            "kind": "customer",
            "permissions": [],
            "iss": "nivaro-identity",
            "aud": "nivaro-browser",
            "iat": instant,
            "exp": instant + 300,
            "jti": str(uuid4()),
        },
        key,
        algorithm="RS256",
        headers={"kid": "test-customer"},
    )
    service_key = tmp_path / "service-key"
    service_key.write_text(secrets.token_hex(48))
    settings = Settings(identity_service_key_file=service_key)
    principal = {
        "user_id": user_id,
        "session_id": session_id,
        "kind": "customer",
        "permissions": [],
    }
    return settings, access, public, principal


@pytest.mark.parametrize(
    "failure", ["network", "timeout", "server", "json", "oversized", "wrong_user", "wrong_kind"]
)
async def test_authorization_fails_closed_on_transport_and_response_failures(
    signed_customer, failure
):
    settings, access, public, principal = signed_customer

    def transport(request):
        if request.url.path == "/.well-known/jwks.json":
            return httpx.Response(200, json={"keys": [public]})
        if failure == "network":
            raise httpx.ConnectError("unavailable", request=request)
        if failure == "timeout":
            raise httpx.ReadTimeout("unavailable", request=request)
        if failure == "server":
            return httpx.Response(503)
        if failure == "json":
            return httpx.Response(200, content=b"invalid")
        if failure == "oversized":
            return httpx.Response(200, content=b" " * 65537)
        if failure == "wrong_user":
            return httpx.Response(200, json={**principal, "user_id": str(uuid4())})
        return httpx.Response(200, json={**principal, "kind": "admin"})

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(transport), base_url="http://identity.test"
    ) as client:
        with pytest.raises(AuthorizationError) as error:
            await IdentityAuthorization(settings, client).check(
                access, mutating=False, origin="", csrf=""
            )
        assert error.value.status == 503


async def test_browser_algorithm_is_restricted_before_network(signed_customer):
    settings, _, _, _ = signed_customer
    token = jwt.encode({"sub": str(uuid4())}, "x" * 64, algorithm="HS256")

    def transport(request):
        pytest.fail("Wrong algorithm must be rejected before reaching identity")

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(transport), base_url="http://identity.test"
    ) as client:
        with pytest.raises(AuthorizationError) as error:
            await IdentityAuthorization(settings, client).check(
                token, mutating=False, origin="", csrf=""
            )
        assert error.value.status == 401
