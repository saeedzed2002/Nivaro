"""Public-key validation plus fresh identity authorization; no shared identity database."""

import asyncio
import hashlib
import json
from time import monotonic, time
from typing import Annotated, Literal
from uuid import UUID, uuid4

import httpx
import jwt
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPublicKey
from fastapi import Depends, Request
from jwt.algorithms import RSAAlgorithm
from pydantic import BaseModel, ConfigDict, ValidationError

from nivaro_cart.domain.errors import AuthorizationError as AuthorizationError
from nivaro_cart.settings import Settings


class CustomerPrincipal(BaseModel):
    model_config = ConfigDict(extra="forbid")
    user_id: UUID
    session_id: UUID
    kind: Literal["customer"]
    permissions: list[str]


class CustomerClaims(BaseModel):
    model_config = ConfigDict(extra="forbid")
    sub: UUID
    sid: UUID
    kind: Literal["customer"]
    permissions: list[str]
    iss: str
    aud: str
    iat: int
    exp: int
    jti: UUID


class IdentityAuthorization:
    def __init__(self, settings: Settings, client: httpx.AsyncClient):
        self.settings, self.client = settings, client
        self.key = None
        if settings.identity_service_key_file:
            self.key = settings.identity_service_key_file.read_text().strip()
            if len(self.key) < 32:
                raise ValueError("Use a dedicated service secret of at least 32 characters")
        self.keys: dict[str, RSAPublicKey] = {}
        self.keys_loaded_at = float("-inf")
        self.key_lock = asyncio.Lock()

    async def _json(
        self,
        method: str,
        path: str,
        *,
        body: dict[str, object] | None = None,
        headers: dict[str, str] | None = None,
    ) -> object:
        # Bound time externally and bytes here; never log response bodies or tokens.
        async with self.client.stream(method, path, json=body, headers=headers) as response:
            if response.status_code in (401, 403):
                raise AuthorizationError(
                    "auth.required" if response.status_code == 401 else "auth.forbidden",
                    response.status_code,
                )
            if response.status_code != 200:
                raise AuthorizationError("auth.unavailable", 503)
            payload = bytearray()
            async for chunk in response.aiter_bytes(chunk_size=8192):
                payload.extend(chunk)
                if len(payload) > 65536:
                    raise AuthorizationError("auth.unavailable", 503)
            return json.loads(payload)

    async def _public_key(self, kid: str) -> RSAPublicKey:
        async with self.key_lock:
            age = monotonic() - self.keys_loaded_at
            if age >= 60 or (kid not in self.keys and age >= 5):
                data = await self._json("GET", "/.well-known/jwks.json")
                if (
                    not isinstance(data, dict)
                    or not isinstance(data.get("keys"), list)
                    or not 1 <= len(data["keys"]) <= 16
                ):
                    raise AuthorizationError("auth.unavailable", 503)
                keys = {}
                for value in data["keys"]:
                    if (
                        not isinstance(value, dict)
                        or value.get("alg") != "RS256"
                        or value.get("use") != "sig"
                        or "d" in value
                    ):
                        raise AuthorizationError("auth.unavailable", 503)
                    key_id = value.get("kid")
                    if not isinstance(key_id, str) or not 1 <= len(key_id) <= 128 or key_id in keys:
                        raise AuthorizationError("auth.unavailable", 503)
                    try:
                        key = RSAAlgorithm.from_jwk(value)
                    except (jwt.PyJWTError, ValueError, TypeError) as exc:
                        raise AuthorizationError("auth.unavailable", 503) from exc
                    if not isinstance(key, RSAPublicKey) or key.key_size < 2048:
                        raise AuthorizationError("auth.unavailable", 503)
                    keys[key_id] = key
                self.keys, self.keys_loaded_at = keys, monotonic()
            if kid not in self.keys:
                raise AuthorizationError("auth.required", 401)
            return self.keys[kid]

    async def check(
        self, access: str, *, mutating: bool, origin: str, csrf: str
    ) -> CustomerPrincipal:
        if not access or len(access) > 8192:
            raise AuthorizationError("auth.required", 401)
        if mutating and (
            origin not in self.settings.allowed_origins or not csrf or len(csrf) > 128
        ):
            raise AuthorizationError("auth.forbidden", 403)
        if self.key is None:
            raise AuthorizationError("auth.unavailable", 503)
        if not mutating:
            origin, csrf = "", ""
        try:
            async with asyncio.timeout(4):
                header = jwt.get_unverified_header(access)
                kid = header.get("kid")
                if (
                    header.get("alg") != "RS256"
                    or not isinstance(kid, str)
                    or not 1 <= len(kid) <= 128
                ):
                    raise AuthorizationError("auth.required", 401)
                key = await self._public_key(kid)
                claims = CustomerClaims.model_validate(
                    jwt.decode(
                        access,
                        key,
                        algorithms=["RS256"],
                        issuer=self.settings.jwt_issuer,
                        audience=self.settings.jwt_audience,
                        options={"require": list(CustomerClaims.model_fields), "strict_aud": True},
                    )
                )
                if claims.permissions:
                    raise AuthorizationError("auth.forbidden", 403)
                body: dict[str, object] = {
                    "access_token": access,
                    "mutating": mutating,
                    "csrf_token": csrf,
                    "origin": origin,
                }
                issued = int(time())
                service = jwt.encode(
                    {
                        "iss": "nivaro-cart",
                        "sub": "cart",
                        "aud": "nivaro-identity-introspection",
                        "kind": "service",
                        "scope": "cart.customer_introspect",
                        "iat": issued,
                        "exp": issued + 30,
                        "jti": str(uuid4()),
                        "body_sha256": hashlib.sha256(
                            json.dumps(body, sort_keys=True, separators=(",", ":")).encode()
                        ).hexdigest(),
                    },
                    self.key,
                    algorithm="HS256",
                )
                raw = await self._json(
                    "POST",
                    "/internal/v1/cart/customer-check",
                    body=body,
                    headers={"Authorization": f"Bearer {service}"},
                )
                try:
                    principal = CustomerPrincipal.model_validate(raw)
                except ValidationError as exc:
                    raise AuthorizationError("auth.unavailable", 503) from exc
                if (
                    principal.user_id != claims.sub
                    or principal.session_id != claims.sid
                    or principal.permissions != claims.permissions
                ):
                    raise AuthorizationError("auth.unavailable", 503)
                return principal
        except (jwt.InvalidTokenError, ValidationError) as exc:
            raise AuthorizationError("auth.required", 401) from exc
        except (httpx.HTTPError, TimeoutError, ValueError, TypeError, KeyError) as exc:
            raise AuthorizationError("auth.unavailable", 503) from exc


async def cart_customer(request: Request) -> CustomerPrincipal:
    if not request.cookies.get("nivaro_customer_access"):
        raise AuthorizationError("auth.required", 401)
    authorization: IdentityAuthorization = request.app.state.authorization
    return await authorization.check(
        request.cookies.get("nivaro_customer_access", ""),
        mutating=request.method not in {"GET", "HEAD"},
        origin=request.headers.get("origin", ""),
        csrf=request.headers.get("x-csrf-token", ""),
    )


CartCustomer = Annotated[CustomerPrincipal, Depends(cart_customer)]
