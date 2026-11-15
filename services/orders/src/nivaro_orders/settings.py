from pathlib import Path
from typing import Self

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import URL

from nivaro_orders.domain.checkout import DeliveryRate


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="ORDERS_", extra="ignore")

    db_host: str = "postgres"
    db_port: int = Field(default=5432, ge=1, le=65535)
    db_name: str = "nivaro_orders"
    db_user: str = "nivaro_orders"
    db_password: SecretStr | None = None
    db_password_file: Path = Path("/run/secrets/orders_db_password")
    db_pool_size: int = Field(default=5, ge=1, le=20)
    delivery_rates: list[DeliveryRate] = Field(default_factory=list)

    @model_validator(mode="after")
    def unique_destinations(self) -> Self:
        if len({(rate.market, rate.country) for rate in self.delivery_rates}) != len(
            self.delivery_rates
        ):
            raise ValueError("Configure one delivery policy per market and destination")
        return self

    def database_url(self) -> URL:
        password = (
            self.db_password.get_secret_value()
            if self.db_password
            else self.db_password_file.read_text(encoding="utf-8").strip()
        )
        if not password:
            raise ValueError("Orders database password must not be empty")
        return URL.create(
            "postgresql+psycopg",
            username=self.db_user,
            password=password,
            host=self.db_host,
            port=self.db_port,
            database=self.db_name,
        )
