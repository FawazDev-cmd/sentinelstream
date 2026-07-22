from datetime import UTC, datetime
from typing import cast
from uuid import UUID

from sqlalchemy import DateTime, Table
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID

from app.domain.logs import LogEvent, LogLevel
from app.infrastructure.database.mapper import map_log_event
from app.infrastructure.database.models import LogEventRecord


def complete_event() -> LogEvent:
    return LogEvent(
        event_id=UUID("12345678-1234-5678-1234-567812345678"),
        timestamp=datetime(2026, 7, 22, 10, tzinfo=UTC),
        received_at=datetime(2026, 7, 22, 10, 0, 1, tzinfo=UTC),
        service="payments",
        environment="test",
        level=LogLevel.ERROR,
        message="failed",
        exception_type="Error",
        exception_message="details",
        latency_ms=12.5,
        status_code=500,
        trace_id="trace",
        request_id="request",
        host="host",
        metadata={"nested": {"items": [1, True]}},  # type: ignore[dict-item]
    )


def test_table_columns_types_nullability_and_indexes() -> None:
    table = cast(Table, LogEventRecord.__table__)
    columns = table.c
    assert table.name == "log_events"
    assert columns.event_id.primary_key
    assert isinstance(columns.event_id.type, PG_UUID)
    assert columns.event_id.type.as_uuid
    assert isinstance(columns.metadata.type, JSONB)
    assert (
        isinstance(columns.timestamp.type, DateTime) and columns.timestamp.type.timezone
    )
    assert (
        isinstance(columns.received_at.type, DateTime)
        and columns.received_at.type.timezone
    )
    for name in (
        "event_id",
        "timestamp",
        "received_at",
        "service",
        "environment",
        "level",
        "message",
        "metadata",
    ):
        assert not columns[name].nullable
    for name in (
        "exception_type",
        "exception_message",
        "latency_ms",
        "status_code",
        "trace_id",
        "request_id",
        "host",
    ):
        assert columns[name].nullable
    assert {index.name for index in table.indexes} == {
        "ix_log_events_timestamp",
        "ix_log_events_received_at",
        "ix_log_events_service",
        "ix_log_events_environment",
        "ix_log_events_level",
        "ix_log_events_service_timestamp",
    }
    composite = next(
        index
        for index in table.indexes
        if index.name == "ix_log_events_service_timestamp"
    )
    assert [column.name for column in composite.columns] == ["service", "timestamp"]


def test_mapping_preserves_values_and_makes_metadata_mutable() -> None:
    source: dict[str, object] = {"nested": {"items": [1, True]}}
    event = complete_event()
    before = event.to_dict()
    record = map_log_event(event)
    assert record.event_id == event.event_id and isinstance(record.event_id, UUID)
    assert (
        record.timestamp is event.timestamp and record.received_at is event.received_at
    )
    assert record.level == "ERROR"
    assert record.exception_type == "Error" and record.status_code == 500
    assert record.event_metadata == source
    assert isinstance(record.event_metadata, dict)
    assert isinstance(record.event_metadata["nested"], dict)
    nested = record.event_metadata["nested"]
    assert isinstance(nested, dict)
    assert isinstance(nested["items"], list)
    nested["items"].append(2)
    assert event.to_dict() == before


def test_minimal_mapping_preserves_optional_none_values_and_metadata_name() -> None:
    event = LogEvent(
        event_id=UUID(int=2),
        timestamp=datetime(2026, 7, 22, tzinfo=UTC),
        received_at=datetime(2026, 7, 22, tzinfo=UTC),
        service="api",
        environment="test",
        level=LogLevel.INFO,
        message="ok",
    )
    record = map_log_event(event)
    assert record.exception_type is None and record.latency_ms is None
    assert record.event_metadata == {}
    assert LogEventRecord.__table__.c.metadata.name == "metadata"
    assert "event_metadata" not in LogEventRecord.__table__.c
