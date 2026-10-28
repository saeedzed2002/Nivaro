"""Restricted, fresh catalog administration checks; never exposed by the gateway."""

import hashlib
import hmac
import json
from time import time
from typing import Literal
from uuid import UUID

import jwt
from pydantic import BaseModel, ConfigDict, Field, StrictBool

from nivaro_identity.domain.errors import IdentityError


class CatalogCheck(BaseModel):
    model_config = ConfigDict(extra="forbid")
    access_token: str = Field(min_length=1, max_length=8192)
    mutating: StrictBool
    csrf_token: str = Field(default="", max_length=128)
    origin: str = Field(default="", max_length=256)

    def fingerprint(self) -> str:
        return hashlib.sha256(
            json.dumps(self.model_dump(), sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()


class CatalogPrincipal(BaseModel):
    user_id: UUID
    session_id: UUID
    kind: Literal["admin"] = "admin"
    permissions: list[str]


def authenticate_catalog(authorization: str, body: CatalogCheck, key: str | None) -> None:
    if key is None:
        raise IdentityError("service.unavailable", 503)
    if not authorization.startswith("Bearer ") or len(authorization) > 2048:
        raise IdentityError("service.invalid")
    try:
        claims = jwt.decode(
            authorization[7:],
            key,
            algorithms=["HS256"],
            issuer="nivaro-catalog",
            audience="nivaro-identity-introspection",
            subject="catalog",
            options={
                "require": [
                    "iss",
                    "aud",
                    "sub",
                    "iat",
                    "exp",
                    "jti",
                    "kind",
                    "scope",
                    "body_sha256",
                ],
                "strict_aud": True,
            },
        )
        if (
            claims["kind"] != "service"
            or claims["scope"] != "catalog.admin_introspect"
            or type(claims["iat"]) is not int
            or type(claims["exp"]) is not int
            or not 0 < claims["exp"] - claims["iat"] <= 30
            or claims["iat"] < int(time()) - 30
            or not isinstance(claims["body_sha256"], str)
            or not hmac.compare_digest(claims["body_sha256"], body.fingerprint())
        ):
            raise ValueError("Invalid service claims")
        UUID(claims["jti"])
    except (jwt.InvalidTokenError, ValueError, TypeError, KeyError) as exc:
        raise IdentityError("service.invalid") from exc
