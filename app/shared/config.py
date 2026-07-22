"""Central application configuration."""

from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    application_name: str = "SentinelStream"
    application_version: str = "0.1.0"
    environment: str = "local"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    json_logging_enabled: bool = True
    event_queue_max_size: int = Field(default=1000, gt=0)
    worker_shutdown_timeout_seconds: float = Field(
        default=10.0, gt=0, allow_inf_nan=False
    )
    database_url: str = "postgresql+asyncpg://sentinelstream:sentinelstream@localhost:5432/sentinelstream"
    database_echo: bool = False
    model_config = SettingsConfigDict(
        env_file=".env", env_prefix="SENTINELSTREAM_", extra="ignore"
    )

    @field_validator("database_url")
    @classmethod
    def database_url_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("database URL must not be blank")
        return value


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
