from pathlib import Path
from typing import Literal, Self

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import URL

from nivaro_cart.domain.limits import Limits


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="CART_", extra="ignore")

    db_host: str = "postgres"
    db_port: int = Field(default=5432, ge=1, le=65535)
    db_name: str = "nivaro_cart"
    db_user: str = "nivaro_cart"
    db_password: SecretStr | None = None
    db_password_file: Path = Path("/run/secrets/cart_db_password")
    db_pool_size: int = Field(default=5, ge=1, le=20)
    log_level: str = "INFO"
    max_variants: int = Field(default=50, ge=1)
    max_lines: int = Field(default=100, ge=1)
    max_units_per_variant: int = Field(default=20, ge=1)
    allowed_origins: list[str] = ["http://127.0.0.1:8080", "http://localhost:8080"]
    identity_url: str = "http://identity:8000"
    catalog_url: str = "http://catalog:8000"
    event_broker_host: str = "rabbitmq"
    event_broker_password_file: Path = Path("/run/secrets/cart_event_broker_password")
    identity_service_key_file: Path | None = None
    jwt_issuer: str = "nivaro-identity"
    jwt_audience: str = "nivaro-browser"
    environment: Literal["development", "test", "release"] = "development"

    @model_validator(mode="after")
    def deployment_safety(self) -> Self:
        if not self.allowed_origins or any(origin.endswith("/") for origin in self.allowed_origins):
            raise ValueError("Use explicit origins without a trailing slash")
        if self.environment == "release" and any(
            not origin.startswith("https://") for origin in self.allowed_origins
        ):
            raise ValueError("Release origins must use HTTPS")
        return self

    def limits(self) -> Limits:
        return Limits(self.max_variants, self.max_lines, self.max_units_per_variant)

    def database_url(self) -> URL:
        password = (
            self.db_password.get_secret_value()
            if self.db_password
            else self.db_password_file.read_text(encoding="utf-8").strip()
        )
        if not password:
            raise ValueError("Cart database password must not be empty")
        return URL.create(
            "postgresql+psycopg",
            username=self.db_user,
            password=password,
            host=self.db_host,
            port=self.db_port,
            database=self.db_name,
        )
