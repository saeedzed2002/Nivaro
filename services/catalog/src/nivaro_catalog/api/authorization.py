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
from pydantic import BaseModel, ConfigDict, StrictInt, ValidationError

from nivaro_catalog.settings import Settings


class AuthorizationError(Exception):
    def __init__(self, code: str, status: int):
        self.code, self.status = code, status


class AdminPrincipal(BaseModel):
    model_config = ConfigDict(extra="forbid")
    user_id: UUID
    session_id: UUID
    kind: Literal["admin"]
    permissions: list[str]


class CustomerPrincipal(BaseModel):
    model_config = ConfigDict(extra="forbid")
    user_id: UUID


class AdminClaims(BaseModel):
    model_config = ConfigDict(extra="forbid")
    sub: UUID
    sid: UUID
    kind: Literal["admin"]
    permissions: list[str]
    iss: str
    aud: str
    iat: int
    exp: int
    jti: UUID


CheckoutScope = Literal["catalog.quote", "catalog.reserve", "catalog.finalize"]


class ServiceClaims(BaseModel):
    model_config = ConfigDict(extra="forbid")
    sub: Literal["orders"]
    kind: Literal["service"]
    scope: str
    iss: str
    aud: str
    iat: StrictInt
    exp: StrictInt
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
            async for chunk in response.aiter_bytes():
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

    async def signed_claims[T: BaseModel](self, access: str, audience: str, contract: type[T]) -> T:
        header = jwt.get_unverified_header(access)
        kid = header.get("kid")
        if header.get("alg") != "RS256" or not isinstance(kid, str) or not 1 <= len(kid) <= 128:
            raise AuthorizationError("auth.required", 401)
        key = await self._public_key(kid)
        return contract.model_validate(
            jwt.decode(
                access,
                key,
                algorithms=["RS256"],
                issuer=self.settings.jwt_issuer,
                audience=audience,
                options={"require": list(contract.model_fields), "strict_aud": True},
            )
        )

    async def check_checkout(self, authorization: str, scope: CheckoutScope) -> None:
        scheme, _, access = authorization.partition(" ")
        if scheme.lower() != "bearer" or not access or len(access) > 8192:
            raise AuthorizationError("auth.required", 401)
        try:
            async with asyncio.timeout(4):
                claims = await self.signed_claims(access, "nivaro-catalog", ServiceClaims)
                if not 0 < claims.exp - claims.iat <= 30:
                    raise AuthorizationError("auth.required", 401)
                if claims.scope != scope:
                    raise AuthorizationError("auth.forbidden", 403)
        except (jwt.InvalidTokenError, ValidationError) as exc:
            raise AuthorizationError("auth.required", 401) from exc
        except (httpx.HTTPError, TimeoutError, ValueError, TypeError, KeyError) as exc:
            raise AuthorizationError("auth.unavailable", 503) from exc

    def _session_body(
        self, access: str, mutating: bool, origin: str, csrf: str
    ) -> dict[str, object]:
        if not access or len(access) > 8192:
            raise AuthorizationError("auth.required", 401)
        if mutating and (
            origin not in self.settings.allowed_origins or not csrf or len(csrf) > 128
        ):
            raise AuthorizationError("auth.forbidden", 403)
        if not mutating:
            origin, csrf = "", ""
        return {"access_token": access, "mutating": mutating, "csrf_token": csrf, "origin": origin}

    async def _introspect(self, path: str, scope: str, body: dict[str, object]) -> object:
        if self.key is None:
            raise AuthorizationError("auth.unavailable", 503)
        issued = int(time())
        service = jwt.encode(
            {
                "iss": "nivaro-catalog",
                "sub": "catalog",
                "aud": "nivaro-identity-introspection",
                "kind": "service",
                "scope": scope,
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
        return await self._json(
            "POST", path, body=body, headers={"Authorization": f"Bearer {service}"}
        )

    async def check_customer(
        self, access: str, *, mutating: bool, origin: str, csrf: str
    ) -> CustomerPrincipal:
        body = self._session_body(access, mutating, origin, csrf)
        try:
            async with asyncio.timeout(4):
                raw = await self._introspect(
                    "/internal/v1/catalog/customer-check", "catalog.customer_introspect", body
                )
                return CustomerPrincipal.model_validate(raw)
        except (httpx.HTTPError, TimeoutError, ValueError, TypeError, KeyError) as exc:
            raise AuthorizationError("auth.unavailable", 503) from exc

    async def check(
        self, access: str, *, mutating: bool, origin: str, csrf: str, moderating: bool = False
    ) -> AdminPrincipal:
        body = self._session_body(access, mutating, origin, csrf)
        if self.key is None:
            raise AuthorizationError("auth.unavailable", 503)
        permission = "reviews.moderate" if moderating else "catalog.write"
        scope = "catalog.moderator_introspect" if moderating else "catalog.admin_introspect"
        path = (
            "/internal/v1/catalog/moderator-check"
            if moderating
            else "/internal/v1/catalog/admin-check"
        )
        try:
            async with asyncio.timeout(4):
                claims = await self.signed_claims(access, self.settings.jwt_audience, AdminClaims)
                if permission not in claims.permissions:
                    raise AuthorizationError("auth.forbidden", 403)
                raw = await self._introspect(path, scope, body)
                try:
                    principal = AdminPrincipal.model_validate(raw)
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


async def catalog_admin(request: Request) -> AdminPrincipal:
    if not request.cookies.get("nivaro_admin_access"):
        raise AuthorizationError("auth.required", 401)
    authorization: IdentityAuthorization = request.app.state.authorization
    return await authorization.check(
        request.cookies.get("nivaro_admin_access", ""),
        mutating=request.method not in {"GET", "HEAD"},
        origin=request.headers.get("origin", ""),
        csrf=request.headers.get("x-csrf-token", ""),
    )


CatalogAdmin = Annotated[AdminPrincipal, Depends(catalog_admin)]
