import asyncio
import json
from collections.abc import Awaitable, Callable
from time import monotonic
from typing import Annotated, Literal
from uuid import UUID

import httpx
import jwt
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPublicKey
from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt.algorithms import RSAAlgorithm
from pydantic import BaseModel, ConfigDict, Field, StrictInt, ValidationError

from nivaro_payments.contracts import PaymentError

type Scope = Literal[
    "payments.start",
    "payments.read",
    "payments.verify",
    "payments.refund",
    "payments.operations.read",
    "payments.operations.reconcile",
]
bearer = HTTPBearer(auto_error=False)


class Claims(BaseModel):
    model_config = ConfigDict(extra="forbid")
    iss: str
    sub: Literal["orders"]
    aud: Literal["nivaro-payments"]
    kind: Literal["service"]
    scope: Scope
    iat: StrictInt
    exp: StrictInt
    jti: UUID


class SigningKey(BaseModel):
    kid: Annotated[str, Field(min_length=1, max_length=80)]
    alg: Literal["RS256"]
    use: Literal["sig"]
    kty: Literal["RSA"]
    e: str
    n: str


class KeySet(BaseModel):
    keys: Annotated[list[SigningKey], Field(min_length=1, max_length=16)]


class OrdersAuthorization:
    def __init__(self, client: httpx.AsyncClient, issuer: str) -> None:
        self.client, self.issuer = client, issuer
        self.keys: dict[str, RSAPublicKey] = {}
        self.loaded_at = float("-inf")
        self.lock = asyncio.Lock()

    async def refresh_keys(self) -> dict[str, RSAPublicKey]:
        try:
            async with (
                asyncio.timeout(5),
                self.client.stream("GET", "/.well-known/jwks.json") as response,
            ):
                response.raise_for_status()
                raw = bytearray()
                async for chunk in response.aiter_bytes(8192):
                    raw.extend(chunk)
                    if len(raw) > 65536:
                        raise ValueError("Signing keys response exceeds its limit")
            keys = {}
            for item in KeySet.model_validate(json.loads(raw)).keys:
                key = RSAAlgorithm.from_jwk(item.model_dump())
                if not isinstance(key, RSAPublicKey) or key.key_size < 2048 or item.kid in keys:
                    raise ValueError("Invalid signing key")
                keys[item.kid] = key
            return keys
        except (ValueError, jwt.PyJWTError, httpx.HTTPError, TimeoutError) as exc:
            raise PaymentError("authorization.unavailable", 503) from exc

    async def key(self, kid: str) -> RSAPublicKey:
        async with self.lock:
            age = monotonic() - self.loaded_at
            if age >= 60 or (kid not in self.keys and age >= 5):
                self.keys = await self.refresh_keys()
                self.loaded_at = monotonic()
            key = self.keys.get(kid)
            if key is None:
                raise jwt.InvalidTokenError("Unknown signing key")
            return key

    async def verify(self, token: str, scope: Scope) -> None:
        try:
            if not token or len(token) > 8192:
                raise jwt.InvalidTokenError("Invalid credential length")
            header = jwt.get_unverified_header(token)
            kid = header.get("kid")
            if header.get("alg") != "RS256" or not isinstance(kid, str) or not 1 <= len(kid) <= 80:
                raise jwt.InvalidTokenError("Invalid signing header")
            claims = Claims.model_validate(
                jwt.decode(
                    token,
                    await self.key(kid),
                    algorithms=["RS256"],
                    issuer=self.issuer,
                    audience="nivaro-payments",
                    subject="orders",
                    options={"strict_aud": True},
                )
            )
            if not 0 < claims.exp - claims.iat <= 30:
                raise jwt.InvalidTokenError("Invalid credential lifetime")
        except (jwt.InvalidTokenError, ValidationError) as exc:
            raise PaymentError("service.unauthorized", 401) from exc
        if claims.scope != scope:
            raise PaymentError("service.forbidden", 403)


def require(scope: Scope) -> Callable[..., Awaitable[None]]:
    async def authorize(
        request: Request,
        credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
    ) -> None:
        if credentials is None:
            raise PaymentError("service.unauthorized", 401)
        authorization: OrdersAuthorization = request.app.state.authorization
        await authorization.verify(credentials.credentials, scope)

    return authorize
