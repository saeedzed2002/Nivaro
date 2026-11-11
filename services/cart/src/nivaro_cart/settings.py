from pathlib import Path

from pydantic import Field, SecretStr
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
