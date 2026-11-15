from pathlib import Path

from pydantic import AnyHttpUrl, Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import URL
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="PAYMENTS_", extra="ignore")

    db_host: str = "postgres"
    db_port: int = Field(default=5432, ge=1, le=65535)
    db_name: str = "nivaro_payments"
    db_user: str = "nivaro_payments"
    db_password_file: Path = Path("/run/secrets/payments_db_password")
    identity_url: AnyHttpUrl = AnyHttpUrl("http://identity:8000")
    identity_issuer: str = "nivaro-identity"
    event_broker_host: str = "rabbitmq"
    event_broker_password_file: Path = Path("/run/secrets/payments_event_broker_password")

    def database_url(self) -> URL:
        password = self.db_password_file.read_text(encoding="utf-8").strip()
        if not password:
            raise ValueError("Payments database password is empty")
        return URL.create(
            "postgresql+psycopg",
            username=self.db_user,
            password=password,
            host=self.db_host,
            port=self.db_port,
            database=self.db_name,
        )


class Database:
    def __init__(self, settings: Settings) -> None:
        self.engine = create_async_engine(
            settings.database_url(),
            pool_pre_ping=True,
            pool_size=5,
            max_overflow=0,
            pool_timeout=5,
            connect_args={"connect_timeout": 5, "options": "-c statement_timeout=5000"},
            hide_parameters=True,
        )
        self.sessions = async_sessionmaker(self.engine, expire_on_commit=False)
