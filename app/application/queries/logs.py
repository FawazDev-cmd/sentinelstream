"""Framework-independent persisted-log query values."""

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from app.domain.logs import LogEvent, LogLevel
from app.domain.logs.models import ENVIRONMENT_MAX_LENGTH, SERVICE_MAX_LENGTH

DEFAULT_LOG_QUERY_LIMIT = 50
MIN_LOG_QUERY_LIMIT = 1
MAX_LOG_QUERY_LIMIT = 100


def _aware_utc(value: datetime, *, field_name: str) -> datetime:
    if not isinstance(value, datetime):
        raise TypeError(f"{field_name} must be a datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
    return value.astimezone(UTC)


def _optional_filter(value: str | None, *, field_name: str, maximum: int) -> None:
    if value is None:
        return
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string")
    if not value.strip():
        raise ValueError(f"{field_name} must not be blank")
    if len(value) > maximum:
        raise ValueError(f"{field_name} must be at most {maximum} characters")


@dataclass(frozen=True, slots=True)
class LogEventCursor:
    timestamp: datetime
    event_id: UUID

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "timestamp", _aware_utc(self.timestamp, field_name="cursor timestamp")
        )
        if not isinstance(self.event_id, UUID):
            raise TypeError("cursor event_id must be a UUID")


@dataclass(frozen=True, slots=True)
class LogEventQuery:
    service: str | None = None
    environment: str | None = None
    level: LogLevel | None = None
    start_time: datetime | None = None
    end_time: datetime | None = None
    limit: int = DEFAULT_LOG_QUERY_LIMIT
    cursor: LogEventCursor | None = None

    def __post_init__(self) -> None:
        _optional_filter(self.service, field_name="service", maximum=SERVICE_MAX_LENGTH)
        _optional_filter(
            self.environment, field_name="environment", maximum=ENVIRONMENT_MAX_LENGTH
        )
        if self.level is not None and not isinstance(self.level, LogLevel):
            raise TypeError("level must be a LogLevel")
        if isinstance(self.limit, bool) or not isinstance(self.limit, int):
            raise TypeError("limit must be an integer")
        if not MIN_LOG_QUERY_LIMIT <= self.limit <= MAX_LOG_QUERY_LIMIT:
            raise ValueError(
                f"limit must be between {MIN_LOG_QUERY_LIMIT} and {MAX_LOG_QUERY_LIMIT}"
            )
        if self.start_time is not None:
            object.__setattr__(
                self, "start_time", _aware_utc(self.start_time, field_name="start_time")
            )
        if self.end_time is not None:
            object.__setattr__(
                self, "end_time", _aware_utc(self.end_time, field_name="end_time")
            )
        if (
            self.start_time is not None
            and self.end_time is not None
            and self.start_time > self.end_time
        ):
            raise ValueError("start_time must not be later than end_time")
        if self.cursor is not None and not isinstance(self.cursor, LogEventCursor):
            raise TypeError("cursor must be a LogEventCursor")


@dataclass(frozen=True, slots=True)
class LogEventPage:
    items: tuple[LogEvent, ...]
    next_cursor: LogEventCursor | None = None
