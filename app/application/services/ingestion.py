"""Normalize validated external log data into trusted queued events."""

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import UUID, uuid4

from app.application.contracts.clock import Clock
from app.application.contracts.event_queue import EventQueue
from app.domain.logs import LogEvent, LogLevel
from app.domain.logs.models import FrozenJsonValue

LEVEL_ALIASES: Mapping[str, LogLevel] = {
    "debug": LogLevel.DEBUG,
    "info": LogLevel.INFO,
    "warn": LogLevel.WARNING,
    "warning": LogLevel.WARNING,
    "error": LogLevel.ERROR,
    "err": LogLevel.ERROR,
    "critical": LogLevel.CRITICAL,
    "fatal": LogLevel.CRITICAL,
}


@dataclass(frozen=True, slots=True)
class IngestionInput:
    timestamp: datetime
    service: str
    environment: str
    level: str
    message: str
    event_id: UUID | None = None
    exception_type: str | None = None
    exception_message: str | None = None
    latency_ms: float | None = None
    status_code: int | None = None
    trace_id: str | None = None
    request_id: str | None = None
    host: str | None = None
    metadata: Mapping[str, FrozenJsonValue] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class IngestionResult:
    event: LogEvent

    @property
    def event_id(self) -> UUID:
        return self.event.event_id


def normalize_log_level(value: str) -> LogLevel:
    try:
        return LEVEL_ALIASES[value.casefold()]
    except (AttributeError, KeyError) as error:
        accepted = ", ".join(sorted(LEVEL_ALIASES))
        raise ValueError(
            f"unknown log level {value!r}; expected one of: {accepted}"
        ) from error


class IngestionService:
    def __init__(
        self, clock: Clock, queue: EventQueue, id_generator: Callable[[], UUID] = uuid4
    ) -> None:
        self._clock = clock
        self._queue = queue
        self._id_generator = id_generator

    async def ingest(self, data: IngestionInput) -> IngestionResult:
        event = LogEvent(
            event_id=data.event_id or self._id_generator(),
            timestamp=self._aware_utc(data.timestamp, field_name="timestamp"),
            received_at=self._aware_utc(self._clock.now(), field_name="clock output"),
            service=data.service,
            environment=data.environment,
            level=normalize_log_level(data.level),
            message=data.message,
            exception_type=data.exception_type,
            exception_message=data.exception_message,
            latency_ms=data.latency_ms,
            status_code=data.status_code,
            trace_id=data.trace_id,
            request_id=data.request_id,
            host=data.host,
            metadata=data.metadata,
        )
        await self._queue.publish(event)
        return IngestionResult(event)

    @staticmethod
    def _aware_utc(value: datetime, *, field_name: str) -> datetime:
        if not isinstance(value, datetime):
            raise TypeError(f"{field_name} must be a datetime")
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError(f"{field_name} must be timezone-aware")
        return value.astimezone(UTC)
