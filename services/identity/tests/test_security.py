import base64
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from nivaro_identity.domain.phone import normalize_phone
from nivaro_identity.domain.security import Tokens, authenticate_value
from nivaro_identity.settings import Settings


@pytest.mark.parametrize(
    "value,expected",
    [
        ("۰۹۱۲ ۳۴۵ ۶۷۸۹", "+989123456789"),
        ("+98 (912) 345-6789", "+989123456789"),
        ("+1 202 555 0100", "+12025550100"),
        ("٠٩١٢٣٤٥٦٧٨٩", "+989123456789"),
    ],
)
def test_phone_normalization(value: str, expected: str) -> None:
    assert normalize_phone(value) == expected


@pytest.mark.parametrize(
    "value", ["9123456789", "+982112345678", "+0989123456789", "+989123456789x", "+12", "test"]
)
def test_phone_rejects_ambiguous_or_invalid(value: str) -> None:
    with pytest.raises(ValueError):
        normalize_phone(value)


def test_hmac_binds_purpose_and_challenge() -> None:
    mac = authenticate_value("x" * 48, "customer-login", "phone", "challenge", "123456")
    assert mac != authenticate_value("x" * 48, "admin-login", "phone", "challenge", "123456")
    assert mac != authenticate_value("x" * 48, "customer-login", "phone", "other", "123456")
    assert mac != authenticate_value("y" * 48, "customer-login", "phone", "challenge", "123456")


def test_release_rejects_mock_and_http() -> None:
    with pytest.raises(ValueError):
        Settings(
            environment="release", otp_provider="mock", allowed_origins=["https://store.example"]
        )
    with pytest.raises(ValueError):
        Settings(environment="release", otp_provider="disabled")


@pytest.fixture
def tokens(tmp_path: Path) -> Tokens:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    path = tmp_path / "key.pem"
    path.write_bytes(
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )
    return Tokens(Settings(jwt_private_key_file=path))


def test_tokens_are_asymmetric_kind_scoped_and_public_only(tokens: Tokens) -> None:
    user, session = uuid4(), uuid4()
    token = tokens.issue(user, session, "customer", [], datetime.now(UTC) + timedelta(days=30))
    claims = tokens.verify(token, "customer")
    assert claims.sub == user and claims.sid == session
    assert claims.exp - claims.iat <= 300
    with pytest.raises(jwt.InvalidTokenError):
        tokens.verify(token, "admin")
    jwk = tokens.public_keys()["keys"][0]
    assert jwk["alg"] == "RS256" and "d" not in jwk and "p" not in jwk
    forged = jwt.encode(
        claims.model_dump(mode="json"), "attacker", algorithm="HS256", headers={"kid": tokens.kid}
    )
    with pytest.raises(jwt.InvalidTokenError):
        tokens.verify(forged, "customer")


def test_expiry_audience_issuer_and_key_are_required(tokens: Tokens) -> None:
    token = tokens.issue(
        uuid4(), uuid4(), "admin", ["orders.read"], datetime.now(UTC) + timedelta(hours=12)
    )
    valid = tokens.verify(token, "admin").model_dump(mode="json")
    for update in [{"aud": "other-service"}, {"iss": "attacker"}, {"exp": 1}]:
        invalid = jwt.encode(
            valid | update, tokens.private_key, algorithm="RS256", headers={"kid": tokens.kid}
        )
        with pytest.raises(jwt.InvalidTokenError):
            tokens.verify(invalid, "admin")
    del valid["sid"]
    missing = jwt.encode(valid, tokens.private_key, algorithm="RS256", headers={"kid": tokens.kid})
    with pytest.raises(jwt.InvalidTokenError):
        tokens.verify(missing, "admin")


def test_customer_cannot_receive_admin_permissions(tokens: Tokens) -> None:
    with pytest.raises(ValueError):
        tokens.issue(
            uuid4(), uuid4(), "customer", ["users.manage"], datetime.now(UTC) + timedelta(days=1)
        )


def test_malformed_key_identifier_is_a_controlled_token_error(tokens: Tokens) -> None:
    # Construct the untrusted header directly; the signing library correctly
    # refuses to generate this malformed header itself.
    token = tokens.issue(uuid4(), uuid4(), "customer", [], datetime.now(UTC) + timedelta(hours=1))
    _, payload, signature = token.split(".")
    header = (
        base64.urlsafe_b64encode(json.dumps({"alg": "RS256", "kid": []}).encode())
        .rstrip(b"=")
        .decode()
    )
    with pytest.raises(jwt.InvalidTokenError):
        tokens.verify(f"{header}.{payload}.{signature}", "customer")


def test_public_key_overlap_accepts_old_unexpired_tokens_only(
    tokens: Tokens, tmp_path: Path
) -> None:
    old_token = tokens.issue(
        uuid4(), uuid4(), "customer", [], datetime.now(UTC) + timedelta(hours=1)
    )
    overlap = tmp_path / "public-overlap.json"
    overlap.write_text(json.dumps(tokens.public_keys()))
    new_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    key_path = tmp_path / "new-key.pem"
    key_path.write_bytes(
        new_key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )
    rotated = Tokens(Settings(jwt_private_key_file=key_path, jwt_previous_public_keys_file=overlap))
    assert rotated.verify(old_token, "customer").kind == "customer"
    assert len(rotated.public_keys()["keys"]) == 2
    retired = Tokens(Settings(jwt_private_key_file=key_path))
    with pytest.raises(jwt.InvalidTokenError):
        retired.verify(old_token, "customer")
    invalid = tokens.public_keys()
    invalid["keys"][0]["d"] = "private-material"
    overlap.write_text(json.dumps(invalid))
    with pytest.raises(ValueError):
        Tokens(Settings(jwt_private_key_file=key_path, jwt_previous_public_keys_file=overlap))
