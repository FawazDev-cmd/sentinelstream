"""Focused domain-to-ORM conversion."""

from collections.abc import Mapping
from typing import cast

from app.domain.logs import LogEvent
from app.domain.logs.models import FrozenJsonValue, JsonValue
from app.infrastructure.database.models import LogEventRecord


def _mutable_json(value: FrozenJsonValue) -> JsonValue:
    if isinstance(value, Mapping):
        return {key: _mutable_json(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_mutable_json(item) for item in value]
    return value


def map_log_event(event: LogEvent) -> LogEventRecord:
    metadata = cast(dict[str, JsonValue], _mutable_json(event.metadata))
    return LogEventRecord(
        event_id=event.event_id,
        timestamp=event.timestamp,
        received_at=event.received_at,
        service=event.service,
        environment=event.environment,
        level=event.level.value,
        message=event.message,
        exception_type=event.exception_type,
        exception_message=event.exception_message,
        latency_ms=event.latency_ms,
        status_code=event.status_code,
        trace_id=event.trace_id,
        request_id=event.request_id,
        host=event.host,
        event_metadata=metadata,
    )
