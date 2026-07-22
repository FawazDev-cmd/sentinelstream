import asyncio
from datetime import UTC, datetime, timedelta, timezone
from uuid import UUID

import pytest

from app.application.exceptions import EventQueueFullError
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


class RecordingQueue:
    def __init__(self, full: bool = False) -> None:
        self.events: list[LogEvent] = []
        self.full = full

    async def publish(self, event: LogEvent) -> None:
        if self.full:
            raise EventQueueFullError
        self.events.append(event)

    async def consume(self) -> LogEvent:
        raise NotImplementedError

    def task_done(self) -> None:
        raise NotImplementedError

    async def join(self) -> None:
        raise NotImplementedError


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


def service(
    clock: datetime = RECEIVED, queue: RecordingQueue | None = None
) -> tuple[IngestionService, RecordingQueue]:
    active_queue = queue or RecordingQueue()
    return IngestionService(
        FixedClock(clock), active_queue, lambda: EVENT_ID
    ), active_queue


def ingest(
    data: IngestionInput, *, active_service: IngestionService | None = None
) -> LogEvent:
    configured = active_service or service()[0]
    return asyncio.run(configured.ingest(data)).event


def test_minimal_input_creates_and_publishes_same_event() -> None:
    configured, queue = service()
    result = asyncio.run(configured.ingest(make_input()))
    assert isinstance(result.event, LogEvent)
    assert queue.events == [result.event]
    assert queue.events[0] is result.event
    assert result.event_id == EVENT_ID
    assert result.event.received_at == RECEIVED


def test_complete_input_preserves_fields_and_supplied_id() -> None:
    supplied = UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")
    event = ingest(
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
    assert event.event_id == supplied
    assert event.to_dict()["metadata"] == {"nested": [1, True]}
    assert (event.exception_type, event.latency_ms, event.status_code) == (
        "Error",
        1.5,
        500,
    )


@pytest.mark.parametrize(("alias", "expected"), list(LEVEL_ALIASES.items()))
def test_aliases_normalize(alias: str, expected: LogLevel) -> None:
    assert ingest(make_input(level=alias)).level is expected


@pytest.mark.parametrize("alias", ["INFO", "WaRn", "CrItIcAl"])
def test_aliases_are_case_insensitive(alias: str) -> None:
    ingest(make_input(level=alias))


def test_unknown_level_is_rejected() -> None:
    with pytest.raises(ValueError, match="unknown log level"):
        ingest(make_input(level="notice"))


def test_non_utc_timestamp_is_normalized() -> None:
    west = timezone(timedelta(hours=1))
    event = ingest(make_input(timestamp=datetime(2026, 7, 22, 11, tzinfo=west)))
    assert event.timestamp == datetime(2026, 7, 22, 10, tzinfo=UTC)
    assert event.timestamp.tzinfo is UTC


@pytest.mark.parametrize("value", [datetime(2026, 7, 22, 10), "bad"])
def test_invalid_timestamp_is_rejected(value: object) -> None:
    with pytest.raises((TypeError, ValueError)):
        ingest(make_input(timestamp=value))


@pytest.mark.parametrize("value", [datetime(2026, 7, 22, 10), "bad"])
def test_invalid_clock_output_is_rejected(value: object) -> None:
    configured, _ = service(value)  # type: ignore[arg-type]
    with pytest.raises((TypeError, ValueError)):
        ingest(make_input(), active_service=configured)


@pytest.mark.parametrize(
    ("field", "value"), [("service", " "), ("environment", ""), ("message", "\t")]
)
def test_domain_remains_final_validation_guard(field: str, value: str) -> None:
    with pytest.raises(ValueError, match="blank"):
        ingest(make_input(**{field: value}))


def test_metadata_is_frozen_by_domain() -> None:
    source: dict[str, object] = {"items": [1]}
    event = ingest(make_input(metadata=source))
    source["items"] = [2]
    assert event.to_dict()["metadata"] == {"items": [1]}


def test_queue_full_propagates_without_result() -> None:
    configured, queue = service(queue=RecordingQueue(full=True))
    with pytest.raises(EventQueueFullError):
        asyncio.run(configured.ingest(make_input()))
    assert queue.events == []
