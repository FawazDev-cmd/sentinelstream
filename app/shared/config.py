"""Central application configuration."""

from functools import lru_cache
from typing import Literal

from pydantic import Field
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
    model_config = SettingsConfigDict(
        env_file=".env", env_prefix="SENTINELSTREAM_", extra="ignore"
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
