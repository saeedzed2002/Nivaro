import hashlib
import hmac
import json
from datetime import UTC, datetime, timedelta
from typing import Literal
from uuid import UUID, uuid4

import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from jwt.algorithms import RSAAlgorithm
from pydantic import BaseModel, ConfigDict, ValidationError

from nivaro_identity.settings import Settings

SessionKind = Literal["customer", "admin"]
Role = Literal["customer", "support_agent", "catalog_manager", "sales_manager", "super_admin"]
ROLE_PERMISSIONS: dict[str, list[str]] = {
    "customer": [],
    "support_agent": ["support.reply"],
    "catalog_manager": ["catalog.write", "reviews.moderate"],
    "sales_manager": ["orders.read"],
    "super_admin": [
        "catalog.write",
        "reviews.moderate",
        "orders.read",
        "payments.refund",
        "support.reply",
        "users.manage",
    ],
}


def digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def authenticate_value(pepper: str, purpose: str, *parts: str) -> str:
    return hmac.new(
        pepper.encode(),
        json.dumps([purpose, *parts], separators=(",", ":")).encode(),
        hashlib.sha256,
    ).hexdigest()


class Claims(BaseModel):
    model_config = ConfigDict(extra="forbid")
    sub: UUID
    sid: UUID
    kind: SessionKind
    permissions: list[str]
    iss: str
    aud: str
    iat: int
    exp: int
    jti: UUID


class Tokens:
    def __init__(self, settings: Settings):
        self.settings = settings
        key = serialization.load_pem_private_key(
            settings.jwt_private_key_file.read_bytes(), password=None
        )
        if not isinstance(key, rsa.RSAPrivateKey) or key.key_size < 2048:
            raise ValueError("Use an RSA private key of at least 2048 bits")
        self.private_key = key
        public = key.public_key()
        self.kid = digest(
            public.public_bytes(
                serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
            ).decode()
        )[:24]
        self.keys: dict[str, rsa.RSAPublicKey] = {self.kid: public}
        if settings.jwt_previous_public_keys_file:
            previous = json.loads(settings.jwt_previous_public_keys_file.read_text())
            for item in previous["keys"]:
                if "d" in item or item.get("alg") != "RS256" or item.get("use") != "sig":
                    raise ValueError("Overlap keys must be public RS256 signing keys")
                if item["kid"] in self.keys:
                    raise ValueError("Duplicate signing key ID")
                imported = RSAAlgorithm.from_jwk(item)
                if not isinstance(imported, rsa.RSAPublicKey) or imported.key_size < 2048:
                    raise ValueError("Invalid overlap key")
                self.keys[item["kid"]] = imported

    def public_keys(self) -> dict[str, list[dict[str, object]]]:
        return {
            "keys": [
                dict(json.loads(RSAAlgorithm.to_jwk(key)), kid=kid, alg="RS256", use="sig")
                for kid, key in self.keys.items()
            ]
        }

    def issue(
        self,
        user_id: UUID,
        session_id: UUID,
        kind: SessionKind,
        permissions: list[str],
        expires_at: datetime,
    ) -> str:
        if kind == "customer" and permissions:
            raise ValueError("Customer sessions cannot carry administrator permissions")
        now = datetime.now(UTC)
        claims = Claims(
            sub=user_id,
            sid=session_id,
            kind=kind,
            permissions=permissions,
            iss=self.settings.jwt_issuer,
            aud=self.settings.jwt_audience,
            iat=int(now.timestamp()),
            exp=int(min(expires_at, now + timedelta(minutes=5)).timestamp()),
            jti=uuid4(),
        )
        return jwt.encode(
            claims.model_dump(mode="json"),
            self.private_key,
            algorithm="RS256",
            headers={"kid": self.kid},
        )

    def issue_service(
        self, client_id: str, audience: str, scope: str, *, customer_id: UUID | None = None
    ) -> str:
        issued_at = int(datetime.now(UTC).timestamp())
        actor = {"customer_id": str(customer_id)} if customer_id is not None else {}
        return jwt.encode(
            {
                "iss": self.settings.jwt_issuer,
                "sub": client_id,
                "aud": audience,
                "kind": "service",
                "scope": scope,
                "iat": issued_at,
                "exp": issued_at + 30,
                "jti": str(uuid4()),
                **actor,
            },
            self.private_key,
            algorithm="RS256",
            headers={"kid": self.kid},
        )

    def address_snapshot_customer(self, token: str) -> UUID:
        header = jwt.get_unverified_header(token)
        kid = header.get("kid")
        if header.get("alg") != "RS256" or not isinstance(kid, str) or kid not in self.keys:
            raise jwt.InvalidTokenError("Unrecognized service signing key")
        claims = jwt.decode(
            token,
            self.keys[kid],
            algorithms=["RS256"],
            issuer=self.settings.jwt_issuer,
            audience="nivaro-identity",
            subject="orders",
            options={
                "require": [
                    "iss",
                    "aud",
                    "sub",
                    "kind",
                    "scope",
                    "iat",
                    "exp",
                    "jti",
                    "customer_id",
                ],
                "strict_aud": True,
            },
        )
        if (
            claims["kind"] != "service"
            or claims["scope"] != "identity.address_snapshot"
            or type(claims["iat"]) is not int
            or type(claims["exp"]) is not int
            or not 0 < claims["exp"] - claims["iat"] <= 30
            or not isinstance(claims["customer_id"], str)
        ):
            raise jwt.InvalidTokenError("Invalid address snapshot grant")
        return UUID(claims["customer_id"])

    def verify(self, token: str, kind: SessionKind) -> Claims:
        header = jwt.get_unverified_header(token)
        kid = header.get("kid")
        if header.get("alg") != "RS256" or not isinstance(kid, str) or kid not in self.keys:
            raise jwt.InvalidTokenError("Unrecognized signing key or algorithm")
        payload = jwt.decode(
            token,
            self.keys[kid],
            algorithms=["RS256"],
            issuer=self.settings.jwt_issuer,
            audience=self.settings.jwt_audience,
            options={"require": list(Claims.model_fields), "strict_aud": True},
        )
        try:
            claims = Claims.model_validate(payload)
        except ValidationError as error:
            raise jwt.InvalidTokenError("Invalid access-token claims") from error
        if claims.kind != kind:
            raise jwt.InvalidTokenError("Wrong session kind")
        if kind == "customer" and claims.permissions:
            raise jwt.InvalidTokenError("Unexpected customer permissions")
        return claims
