from pathlib import Path
from typing import Literal, Self

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import URL


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="IDENTITY_", extra="ignore")

    environment: Literal["development", "test", "release"] = "development"
    otp_provider: Literal["mock", "disabled"] = "disabled"
    mock_phones: list[str] = []
    allowed_origins: list[str] = ["http://127.0.0.1:8080", "http://localhost:8080"]
    db_host: str = "postgres"
    db_port: int = Field(default=5432, ge=1, le=65535)
    db_name: str = "nivaro_identity"
    db_user: str = "nivaro_identity"
    db_password_file: Path = Path("/run/secrets/identity_db_password")
    redis_host: str = "redis-state"
    redis_port: int = Field(default=6379, ge=1, le=65535)
    redis_password_file: Path = Path("/run/secrets/redis_state_password")
    otp_pepper_file: Path = Path("/run/secrets/otp_pepper")
    jwt_private_key_file: Path = Path("/run/secrets/identity_signing_key")
    jwt_previous_public_keys_file: Path | None = None
    jwt_issuer: str = "nivaro-identity"
    jwt_audience: str = "nivaro-browser"
    otp_ip_limit: int = Field(default=30, ge=1, le=100)
    trust_gateway_client_ip: bool = False

    @model_validator(mode="after")
    def deployment_safety(self) -> Self:
        if self.environment == "release":
            if self.otp_provider == "mock":
                raise ValueError("Mock login cannot run in a release environment")
            if any(not origin.startswith("https://") for origin in self.allowed_origins):
                raise ValueError("Release origins must use HTTPS")
        if not self.allowed_origins or any(origin.endswith("/") for origin in self.allowed_origins):
            raise ValueError("Use explicit origins without a trailing slash")
        return self

    def secret(self, path: Path) -> str:
        value = path.read_text(encoding="utf-8").strip()
        if len(value) < 32:
            raise ValueError("Identity secrets must contain at least 32 characters")
        return value

    def database_url(self) -> URL:
        return URL.create(
            "postgresql+psycopg",
            username=self.db_user,
            password=self.secret(self.db_password_file),
            host=self.db_host,
            port=self.db_port,
            database=self.db_name,
        )
