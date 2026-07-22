from datetime import UTC, datetime, timedelta, timezone
from uuid import UUID

import pytest

from app.application.services.ingestion import (
    LEVEL_ALIASES,
    IngestionInput,
    IngestionService,
)
from app.domain.logs import LogEvent, LogLevel

EVENT_ID = UUID("12345678-1234-5678-1234-567812345678")
RECEIVED = datetime(2026, 7, 22, 12, tzinfo=UTC)


class FixedClock:
    def __init__(self, value: datetime) -> None:
        self.value = value

    def now(self) -> datetime:
        return self.value


def make_input(**overrides: object) -> IngestionInput:
    values: dict[str, object] = {
        "timestamp": datetime(2026, 7, 22, 10, tzinfo=UTC),
        "service": "api",
        "environment": "test",
        "level": "info",
        "message": "ready",
    }
    values.update(overrides)
    return IngestionInput(**values)  # type: ignore[arg-type]


def service(clock: datetime = RECEIVED) -> IngestionService:
    return IngestionService(FixedClock(clock), lambda: EVENT_ID)


def test_minimal_input_creates_event_and_uses_injected_values() -> None:
    result = service().ingest(make_input())
    assert isinstance(result.event, LogEvent)
    assert result.event_id == EVENT_ID
    assert result.event.received_at == RECEIVED


def test_complete_input_preserves_fields_and_supplied_id() -> None:
    supplied = UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")
    event = (
        service()
        .ingest(
            make_input(
                event_id=supplied,
                exception_type="Error",
                exception_message="bad",
                latency_ms=1.5,
                status_code=500,
                trace_id="t",
                request_id="r",
                host="h",
                metadata={"nested": [1, True]},
            )
        )
        .event
    )
    assert event.event_id == supplied
    assert event.to_dict()["metadata"] == {"nested": [1, True]}
    assert (event.exception_type, event.latency_ms, event.status_code) == (
        "Error",
        1.5,
        500,
    )


@pytest.mark.parametrize(("alias", "expected"), list(LEVEL_ALIASES.items()))
def test_aliases_normalize(alias: str, expected: LogLevel) -> None:
    assert service().ingest(make_input(level=alias)).event.level is expected


@pytest.mark.parametrize("alias", ["INFO", "WaRn", "CrItIcAl"])
def test_aliases_are_case_insensitive(alias: str) -> None:
    service().ingest(make_input(level=alias))


def test_unknown_level_is_rejected() -> None:
    with pytest.raises(ValueError, match="unknown log level"):
        service().ingest(make_input(level="notice"))


def test_non_utc_timestamp_is_normalized() -> None:
    west = timezone(timedelta(hours=1))
    event = (
        service()
        .ingest(make_input(timestamp=datetime(2026, 7, 22, 11, tzinfo=west)))
        .event
    )
    assert event.timestamp == datetime(2026, 7, 22, 10, tzinfo=UTC)
    assert event.timestamp.tzinfo is UTC


@pytest.mark.parametrize("value", [datetime(2026, 7, 22, 10), "bad"])
def test_invalid_timestamp_is_rejected(value: object) -> None:
    with pytest.raises((TypeError, ValueError)):
        service().ingest(make_input(timestamp=value))


@pytest.mark.parametrize("value", [datetime(2026, 7, 22, 10), "bad"])
def test_invalid_clock_output_is_rejected(value: object) -> None:
    with pytest.raises((TypeError, ValueError)):
        service(value).ingest(make_input())  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("field", "value"), [("service", " "), ("environment", ""), ("message", "\t")]
)
def test_domain_remains_final_validation_guard(field: str, value: str) -> None:
    with pytest.raises(ValueError, match="blank"):
        service().ingest(make_input(**{field: value}))


def test_metadata_is_frozen_by_domain() -> None:
    source: dict[str, object] = {"items": [1]}
    event = service().ingest(make_input(metadata=source)).event
    source["items"] = [2]
    assert event.to_dict()["metadata"] == {"items": [1]}
