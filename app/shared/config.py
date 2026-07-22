"""Central application configuration."""

from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator, model_validator
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
    high_latency_threshold_ms: float = Field(default=1000.0, gt=0, allow_inf_nan=False)
    critical_latency_threshold_ms: float = Field(
        default=5000.0, gt=0, allow_inf_nan=False
    )
    server_error_min_status: int = Field(default=500, ge=500, le=599)
    critical_server_error_min_status: int = Field(default=550, ge=500, le=599)
    database_url: str = "postgresql+asyncpg://sentinelstream:sentinelstream@localhost:5432/sentinelstream"
    database_echo: bool = False
    incident_generation_lookback_seconds: int = Field(default=3600, ge=1, le=86_400)
    model_config = SettingsConfigDict(
        env_file=".env", env_prefix="SENTINELSTREAM_", extra="ignore"
    )

    @model_validator(mode="after")
    def detection_thresholds_are_ordered(self) -> "Settings":
        if self.critical_latency_threshold_ms < self.high_latency_threshold_ms:
            raise ValueError(
                "critical latency threshold must be greater than or equal to "
                "high latency threshold"
            )
        if self.critical_server_error_min_status < self.server_error_min_status:
            raise ValueError(
                "critical server-error status must be greater than or equal to "
                "server-error status"
            )
        return self

    @field_validator("database_url")
    @classmethod
    def database_url_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("database URL must not be blank")
        return value


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
