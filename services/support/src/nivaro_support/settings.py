from pathlib import Path

from pydantic import AnyHttpUrl, Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import URL
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="SUPPORT_", extra="ignore")

    db_host: str = "postgres"
    db_password_file: Path = Path("/run/secrets/support_db_password")
    db_pool_size: int = Field(default=5, ge=1, le=20)
    identity_url: AnyHttpUrl = AnyHttpUrl("http://identity:8000")
    identity_key_file: Path = Path("/run/secrets/support_identity_service_key")
    allowed_origins: list[str] = ["http://127.0.0.1:8080", "http://localhost:8080"]

    def database_url(self) -> URL:
        password = self.db_password_file.read_text(encoding="utf-8").strip()
        if not password:
            raise ValueError("Support database password is required")
        return URL.create(
            "postgresql+psycopg",
            username="nivaro_support",
            password=password,
            host=self.db_host,
            database="nivaro_support",
        )


class Database:
    def __init__(self, settings: Settings):
        self.engine = create_async_engine(
            settings.database_url(),
            pool_pre_ping=True,
            pool_size=settings.db_pool_size,
            max_overflow=0,
            pool_timeout=5,
            hide_parameters=True,
            connect_args={"connect_timeout": 5, "options": "-c statement_timeout=5000"},
        )
        self.sessions = async_sessionmaker(self.engine, expire_on_commit=False)
