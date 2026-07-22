"""Tests for normalized log-event domain contracts."""

import json
import math
from dataclasses import FrozenInstanceError
from datetime import UTC, datetime, timedelta, timezone
from uuid import UUID

import pytest

from app.domain.logs import LogEvent, LogLevel
from app.domain.logs.models import (
    EXCEPTION_MESSAGE_MAX_LENGTH,
    EXCEPTION_TYPE_MAX_LENGTH,
    HOST_MAX_LENGTH,
    MESSAGE_MAX_LENGTH,
    METADATA_MAX_DEPTH,
    REQUEST_ID_MAX_LENGTH,
    SERVICE_MAX_LENGTH,
    TRACE_ID_MAX_LENGTH,
)

EVENT_ID = UUID("12345678-1234-5678-1234-567812345678")
OCCURRED_AT = datetime(2026, 7, 21, 10, 30, tzinfo=UTC)
RECEIVED_AT = datetime(2026, 7, 21, 10, 30, 1, tzinfo=UTC)


def make_event(**overrides: object) -> LogEvent:
    values: dict[str, object] = {
        "event_id": EVENT_ID,
        "timestamp": OCCURRED_AT,
        "received_at": RECEIVED_AT,
        "service": "api",
        "environment": "test",
        "level": LogLevel.INFO,
        "message": "request completed",
    }
    values.update(overrides)
    return LogEvent(**values)  # type: ignore[arg-type]


def test_complete_valid_event_can_be_created() -> None:
    event = make_event(
        exception_type=" TimeoutError ",
        exception_message=" upstream timed out ",
        latency_ms=12.5,
        status_code=504,
        trace_id=" trace-1 ",
        request_id=" request-1 ",
        host=" api-01 ",
        metadata={"retry": True, "attempt": 2},
    )

    assert event.exception_type == "TimeoutError"
    assert event.exception_message == "upstream timed out"
    assert event.latency_ms == 12.5
    assert event.status_code == 504
    assert event.trace_id == "trace-1"
    assert event.request_id == "request-1"
    assert event.host == "api-01"


def test_minimal_event_has_independent_empty_metadata() -> None:
    first = make_event()
    second = make_event(event_id=UUID("87654321-4321-8765-4321-876543218765"))

    assert first.metadata == {}
    assert second.metadata == {}
    assert first.metadata is not second.metadata


@pytest.mark.parametrize("level", list(LogLevel))
def test_every_log_level_is_supported(level: LogLevel) -> None:
    assert make_event(level=level).level is level


@pytest.mark.parametrize("field_name", ["timestamp", "received_at"])
def test_naive_timestamps_are_rejected(field_name: str) -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        make_event(**{field_name: datetime(2026, 7, 21, 10, 30)})


def test_aware_timestamps_are_normalized_to_utc() -> None:
    west_africa = timezone(timedelta(hours=1))
    event = make_event(timestamp=datetime(2026, 7, 21, 11, 30, tzinfo=west_africa))

    assert event.timestamp == OCCURRED_AT
    assert event.timestamp.tzinfo is UTC
    assert make_event().received_at == RECEIVED_AT


@pytest.mark.parametrize("field_name", ["service", "environment", "message"])
def test_required_text_rejects_blank_values(field_name: str) -> None:
    with pytest.raises(ValueError, match="blank"):
        make_event(**{field_name: " \t "})


@pytest.mark.parametrize(
    ("field_name", "maximum"),
    [
        ("service", SERVICE_MAX_LENGTH),
        ("message", MESSAGE_MAX_LENGTH),
        ("exception_type", EXCEPTION_TYPE_MAX_LENGTH),
        ("exception_message", EXCEPTION_MESSAGE_MAX_LENGTH),
        ("trace_id", TRACE_ID_MAX_LENGTH),
        ("request_id", REQUEST_ID_MAX_LENGTH),
        ("host", HOST_MAX_LENGTH),
    ],
)
def test_overlong_bounded_fields_are_rejected(field_name: str, maximum: int) -> None:
    with pytest.raises(ValueError, match="at most"):
        make_event(**{field_name: "x" * (maximum + 1)})


@pytest.mark.parametrize("latency", [-0.1, math.nan, math.inf, -math.inf])
def test_invalid_latency_is_rejected(latency: float) -> None:
    with pytest.raises(ValueError, match="finite and non-negative"):
        make_event(latency_ms=latency)


@pytest.mark.parametrize("status_code", [99, 600])
def test_out_of_range_status_codes_are_rejected(status_code: int) -> None:
    with pytest.raises(ValueError, match="between 100 and 599"):
        make_event(status_code=status_code)


@pytest.mark.parametrize("status_code", [100, 599])
def test_boundary_status_codes_are_accepted(status_code: int) -> None:
    assert make_event(status_code=status_code).status_code == status_code


def test_valid_nested_metadata_is_accepted_and_frozen() -> None:
    event = make_event(metadata={"http": {"tags": ["public", 2, True, None]}})

    assert event.to_dict()["metadata"] == {"http": {"tags": ["public", 2, True, None]}}


def test_non_string_metadata_keys_are_rejected() -> None:
    with pytest.raises(TypeError, match="keys must be strings"):
        make_event(metadata={1: "value"})


@pytest.mark.parametrize("value", [b"bytes", {"set"}, ("tuple",), object()])
def test_unsupported_metadata_values_are_rejected(value: object) -> None:
    with pytest.raises(TypeError, match="unsupported metadata value"):
        make_event(metadata={"value": value})


def test_excessive_metadata_nesting_is_rejected() -> None:
    nested: object = "leaf"
    for _ in range(METADATA_MAX_DEPTH + 1):
        nested = {"child": nested}

    with pytest.raises(ValueError, match="nesting"):
        make_event(metadata={"root": nested})


@pytest.mark.parametrize("value", [math.nan, math.inf, -math.inf])
def test_non_finite_metadata_floats_are_rejected(value: float) -> None:
    with pytest.raises(ValueError, match="floats must be finite"):
        make_event(metadata={"value": value})


def test_metadata_is_defensively_copied_and_event_is_immutable() -> None:
    source: dict[str, object] = {"nested": {"items": [1]}}
    event = make_event(metadata=source)
    source["nested"] = "changed"

    assert event.to_dict()["metadata"] == {"nested": {"items": [1]}}
    with pytest.raises(TypeError):
        event.metadata["new"] = "value"  # type: ignore[index]
    with pytest.raises(FrozenInstanceError):
        event.service = "changed"  # type: ignore[misc]


def test_serialization_is_predictable_and_json_compatible() -> None:
    payload = make_event(metadata={"version": 1}).to_dict()

    assert payload["event_id"] == str(EVENT_ID)
    assert payload["timestamp"] == "2026-07-21T10:30:00+00:00"
    assert payload["level"] == "INFO"
    assert json.loads(json.dumps(payload)) == payload
