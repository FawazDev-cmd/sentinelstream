from collections.abc import Iterator
from datetime import UTC, datetime
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from app.application.queries.cursor import encode_log_event_cursor
from app.application.queries.logs import LogEventCursor, LogEventPage, LogEventQuery
from app.application.services.processor import LoggingEventProcessor
from app.domain.logs import LogEvent, LogLevel
from app.presentation.api import main
from app.shared.config import Settings


class FakeReader:
    def __init__(
        self, page: LogEventPage | None = None, failure: Exception | None = None
    ) -> None:
        self.page = page or LogEventPage(())
        self.failure = failure
        self.queries: list[LogEventQuery] = []

    async def list(self, query: LogEventQuery) -> LogEventPage:
        self.queries.append(query)
        if self.failure is not None:
            raise self.failure
        return self.page


def complete_event() -> LogEvent:
    return LogEvent(
        event_id=UUID("c54b1ea9-a909-4a84-8419-b1f17312e922"),
        timestamp=datetime(2026, 7, 22, 10, tzinfo=UTC),
        received_at=datetime(2026, 7, 22, 10, 0, 1, tzinfo=UTC),
        service="payments-api",
        environment="development",
        level=LogLevel.ERROR,
        message="Payment failed",
        exception_type="PaymentError",
        exception_message="gateway",
        latency_ms=245.5,
        status_code=500,
        trace_id="trace",
        request_id="request",
        host="host",
        metadata={"source": "test"},
    )


@pytest.fixture
def api(test_settings: Settings) -> Iterator[tuple[TestClient, FakeReader]]:
    reader = FakeReader()
    with TestClient(
        main.create_app(
            test_settings,
            event_processor=LoggingEventProcessor(),
            log_event_reader=reader,
        )
    ) as client:
        yield client, reader


def test_empty_results_and_default_limit(api: tuple[TestClient, FakeReader]) -> None:
    client, reader = api
    response = client.get("/api/v1/logs")
    assert response.status_code == 200 and response.json() == {
        "items": [],
        "next_cursor": None,
    }
    assert reader.queries == [LogEventQuery()]


def test_results_serialize_all_fields_and_next_cursor(test_settings: Settings) -> None:
    event = complete_event()
    cursor = LogEventCursor(event.timestamp, event.event_id)
    reader = FakeReader(LogEventPage((event,), cursor))
    with TestClient(
        main.create_app(
            test_settings,
            event_processor=LoggingEventProcessor(),
            log_event_reader=reader,
        )
    ) as client:
        response = client.get("/api/v1/logs")
    body = response.json()
    assert response.status_code == 200
    assert body["next_cursor"] == encode_log_event_cursor(cursor)
    assert body["items"][0] == {
        "event_id": str(event.event_id),
        "timestamp": "2026-07-22T10:00:00Z",
        "received_at": "2026-07-22T10:00:01Z",
        "service": "payments-api",
        "environment": "development",
        "level": "ERROR",
        "message": "Payment failed",
        "exception_type": "PaymentError",
        "exception_message": "gateway",
        "latency_ms": 245.5,
        "status_code": 500,
        "trace_id": "trace",
        "request_id": "request",
        "host": "host",
        "metadata": {"source": "test"},
    }


def test_filters_level_times_limit_and_cursor_are_passed(
    api: tuple[TestClient, FakeReader],
) -> None:
    client, reader = api
    cursor = LogEventCursor(datetime(2026, 7, 22, 9, tzinfo=UTC), UUID(int=3))
    encoded = encode_log_event_cursor(cursor)
    response = client.get(
        "/api/v1/logs",
        params={
            "service": "payments-api",
            "environment": "development",
            "level": "error",
            "start_time": "2026-07-22T00:00:00Z",
            "end_time": "2026-07-22T23:59:59Z",
            "limit": 25,
            "cursor": encoded,
        },
    )
    assert response.status_code == 200
    assert reader.queries == [
        LogEventQuery(
            service="payments-api",
            environment="development",
            level=LogLevel.ERROR,
            start_time=datetime(2026, 7, 22, tzinfo=UTC),
            end_time=datetime(2026, 7, 22, 23, 59, 59, tzinfo=UTC),
            limit=25,
            cursor=cursor,
        )
    ]


@pytest.mark.parametrize(
    ("params", "detail"),
    [
        ({"cursor": "%%%"}, "Invalid pagination cursor."),
        ({"limit": 0}, None),
        ({"limit": 101}, None),
        ({"start_time": "2026-07-22T10:00:00"}, "timezone-aware"),
        ({"end_time": "2026-07-22T10:00:00"}, "timezone-aware"),
        (
            {"start_time": "2026-07-23T00:00:00Z", "end_time": "2026-07-22T00:00:00Z"},
            "later",
        ),
        ({"level": "notice"}, "unknown log level"),
    ],
)
def test_invalid_query_values_return_422(
    api: tuple[TestClient, FakeReader], params: dict[str, object], detail: str | None
) -> None:
    response = api[0].get("/api/v1/logs", params=params)
    assert response.status_code == 422
    if detail is not None:
        assert detail in str(response.json()["detail"])


def test_reader_failure_is_safe_500(test_settings: Settings) -> None:
    reader = FakeReader(
        failure=RuntimeError("postgresql+asyncpg://user:secret@host/db")
    )
    app = main.create_app(
        test_settings, event_processor=LoggingEventProcessor(), log_event_reader=reader
    )
    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get("/api/v1/logs")
    assert response.status_code == 500
    assert "secret" not in response.text and "postgresql" not in response.text


def test_injected_processor_and_reader_bypass_database(
    monkeypatch: pytest.MonkeyPatch, test_settings: Settings
) -> None:
    monkeypatch.setattr(
        main,
        "create_async_engine_from_settings",
        lambda settings: (_ for _ in ()).throw(AssertionError("engine created")),
    )
    with TestClient(
        main.create_app(
            test_settings,
            event_processor=LoggingEventProcessor(),
            log_event_reader=FakeReader(),
        )
    ) as client:
        assert client.get("/api/v1/logs").status_code == 200
