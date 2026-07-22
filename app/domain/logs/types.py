"""Types shared by normalized log-event domain models."""

from enum import StrEnum


class LogLevel(StrEnum):
    """A provider-independent normalized log severity."""

    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"
