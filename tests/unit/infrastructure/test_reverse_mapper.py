from copy import deepcopy
from datetime import UTC, datetime
from uuid import UUID

import pytest

from app.domain.logs import LogEvent, LogLevel
from app.infrastructure.database.mapper import map_log_event, map_log_event_record


def complete_record() -> object:
    event = LogEvent(
        event_id=UUID(int=7),
        timestamp=datetime(2026, 7, 22, 10, tzinfo=UTC),
        received_at=datetime(2026, 7, 22, 10, 0, 1, tzinfo=UTC),
        service="api",
        environment="test",
        level=LogLevel.ERROR,
        message="failed",
        exception_type="Error",
        exception_message="detail",
        latency_ms=12.5,
        status_code=500,
        trace_id="trace",
        request_id="request",
        host="host",
        metadata={"nested": {"items": [1, True]}},  # type: ignore[dict-item]
    )
    return map_log_event(event)


def test_complete_record_maps_to_domain_without_mutating_record() -> None:
    record = complete_record()
    before = deepcopy(record.event_metadata)  # type: ignore[attr-defined]
    event = map_log_event_record(record)  # type: ignore[arg-type]
    assert event.event_id == UUID(int=7) and event.level is LogLevel.ERROR
    assert event.timestamp == datetime(2026, 7, 22, 10, tzinfo=UTC)
    assert event.exception_type == "Error" and event.status_code == 500
    assert event.to_dict()["metadata"] == {"nested": {"items": [1, True]}}
    assert record.event_metadata == before  # type: ignore[attr-defined]


def test_minimal_record_preserves_optional_nulls() -> None:
    source = LogEvent(
        event_id=UUID(int=8),
        timestamp=datetime(2026, 7, 22, tzinfo=UTC),
        received_at=datetime(2026, 7, 22, tzinfo=UTC),
        service="api",
        environment="test",
        level=LogLevel.INFO,
        message="ok",
    )
    event = map_log_event_record(map_log_event(source))
    assert event.event_id == source.event_id and event.exception_type is None
    assert event.latency_ms is None and event.metadata == {}


def test_invalid_persisted_value_fails_visibly() -> None:
    record = complete_record()
    record.service = " "  # type: ignore[attr-defined]
    with pytest.raises(ValueError, match="blank"):
        map_log_event_record(record)  # type: ignore[arg-type]
