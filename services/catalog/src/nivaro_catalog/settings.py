from pathlib import Path

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import URL


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="CATALOG_", extra="ignore")

    cache_host: str | None = None
    cache_password_file: Path = Path("/run/secrets/redis_cache_password")
    db_host: str = "postgres"
    db_port: int = Field(default=5432, ge=1, le=65535)
    db_name: str = "nivaro_catalog"
    db_user: str = "nivaro_catalog"
    db_password: SecretStr | None = None
    db_password_file: Path = Path("/run/secrets/catalog_db_password")
    db_pool_size: int = Field(default=5, ge=1, le=20)
    log_level: str = "INFO"
    identity_url: str = "http://identity:8000"
    identity_service_key_file: Path | None = None
    allowed_origins: list[str] = ["http://127.0.0.1:8080", "http://localhost:8080"]
    jwt_issuer: str = "nivaro-identity"
    jwt_audience: str = "nivaro-browser"
    media_private_root: Path = Path("/var/lib/nivaro-media/private")
    media_output_root: Path = Path("/var/lib/nivaro-media/outputs")
    media_broker_host: str = "rabbitmq"
    media_broker_user: str = "nivaro_catalog_media"
    media_broker_password_file: Path = Path("/run/secrets/catalog_media_broker_password")
    event_broker_host: str = "rabbitmq"
    event_broker_password_file: Path = Path("/run/secrets/catalog_event_broker_password")

    def database_url(self) -> URL:
        password = (
            self.db_password.get_secret_value()
            if self.db_password
            else self.db_password_file.read_text(encoding="utf-8").strip()
        )
        if not password:
            raise ValueError("Catalog database password must not be empty")
        return URL.create(
            "postgresql+psycopg",
            username=self.db_user,
            password=password,
            host=self.db_host,
            port=self.db_port,
            database=self.db_name,
        )
