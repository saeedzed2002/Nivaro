"""Restricted, fresh session checks; never exposed by the gateway."""

import hashlib
import hmac
import json
from time import time
from typing import Literal
from uuid import UUID

import jwt
from pydantic import BaseModel, ConfigDict, Field, StrictBool

from nivaro_identity.domain.errors import IdentityError
from nivaro_identity.domain.security import SessionKind

CATALOG_CUSTOMER_CHECK_PATH = "/internal/v1/catalog/customer-check"
CATALOG_MODERATOR_CHECK_PATH = "/internal/v1/catalog/moderator-check"
SUPPORT_CHECK_PATH = "/internal/v1/support/session-check"


class CatalogCheck(BaseModel):
    model_config = ConfigDict(extra="forbid")
    access_token: str = Field(min_length=1, max_length=8192)
    mutating: StrictBool
    csrf_token: str = Field(default="", max_length=128)
    origin: str = Field(default="", max_length=256)

    def fingerprint(self) -> str:
        return hashlib.sha256(
            json.dumps(self.model_dump(mode="json"), sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()


class CatalogPrincipal(BaseModel):
    user_id: UUID
    session_id: UUID
    kind: Literal["admin"] = "admin"
    permissions: list[str]


class CartCheck(CatalogCheck):
    """Same bounded request shape, with a separate customer-only authority."""


class CartPrincipal(BaseModel):
    user_id: UUID
    session_id: UUID
    kind: Literal["customer"] = "customer"
    permissions: list[str] = Field(default_factory=list)


class CatalogCustomerPrincipal(BaseModel):
    user_id: UUID


class SupportCheck(CatalogCheck):
    kind: SessionKind
    target_agent_id: UUID | None = None


class SupportPrincipal(BaseModel):
    user_id: UUID
    kind: SessionKind
    can_manage: bool


def authenticate_support(authorization: str, body: SupportCheck, key: str | None) -> None:
    _authenticate_service(authorization, body, key, "support", "support.session_introspect")


def authenticate_catalog(authorization: str, body: CatalogCheck, key: str | None) -> None:
    _authenticate_service(authorization, body, key, "catalog", "catalog.admin_introspect")


def authenticate_catalog_customer(authorization: str, body: CatalogCheck, key: str | None) -> None:
    _authenticate_service(authorization, body, key, "catalog", "catalog.customer_introspect")


def authenticate_catalog_moderator(authorization: str, body: CatalogCheck, key: str | None) -> None:
    _authenticate_service(authorization, body, key, "catalog", "catalog.moderator_introspect")


def authenticate_cart(authorization: str, body: CartCheck, key: str | None) -> None:
    _authenticate_service(authorization, body, key, "cart", "cart.customer_introspect")


def _authenticate_service(
    authorization: str, body: CatalogCheck, key: str | None, service: str, scope: str
) -> None:
    if key is None:
        raise IdentityError("service.unavailable", 503)
    if not authorization.startswith("Bearer ") or len(authorization) > 2048:
        raise IdentityError("service.invalid")
    try:
        claims = jwt.decode(
            authorization[7:],
            key,
            algorithms=["HS256"],
            issuer=f"nivaro-{service}",
            audience="nivaro-identity-introspection",
            subject=service,
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
            or claims["scope"] != scope
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
