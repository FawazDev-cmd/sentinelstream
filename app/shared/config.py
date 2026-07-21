"""Central application configuration."""

from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configuration loaded from defaults, .env, and the environment."""

    application_name: str = "SentinelStream"
    application_version: str = "0.1.0"
    environment: str = "local"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    json_logging_enabled: bool = True

    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="SENTINELSTREAM_",
        extra="ignore",
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the stable process-wide settings instance."""

    return Settings()
