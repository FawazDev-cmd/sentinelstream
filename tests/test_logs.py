import asyncio
from collections.abc import Iterator
from datetime import UTC, datetime
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from app.application.exceptions import EventQueueFullError
from app.application.services.processor import LoggingEventProcessor
from app.domain.logs import LogEvent
from app.presentation.api.dependencies import get_ingestion_service
from app.presentation.api.main import create_app
from app.shared.config import Settings

EVENT_ID = UUID("12345678-1234-5678-1234-567812345678")


class FixedClock:
    def now(self) -> datetime:
        return datetime(2026, 7, 22, 12, tzinfo=UTC)


class RecordingQueue:
    def __init__(self, full: bool = False) -> None:
        self.events: list[LogEvent] = []
        self.full = full

    async def publish(self, event: LogEvent) -> None:
        if self.full:
            raise EventQueueFullError
        self.events.append(event)

    async def consume(self) -> LogEvent:
        await asyncio.Future()
        raise AssertionError

    def task_done(self) -> None:
        pass

    async def join(self) -> None:
        pass


def payload() -> dict[str, object]:
    return {
        "timestamp": "2026-07-22T13:00:00+01:00",
        "service": "api",
        "environment": "test",
        "level": "warn",
        "message": "slow",
    }


@pytest.fixture
def queue() -> RecordingQueue:
    return RecordingQueue()


@pytest.fixture
def ingestion_client(
    test_settings: Settings, queue: RecordingQueue
) -> Iterator[TestClient]:
    with TestClient(
        create_app(
            test_settings,
            event_queue=queue,
            clock=FixedClock(),
            event_id_factory=lambda: EVENT_ID,
            event_processor=LoggingEventProcessor(),
        )
    ) as client:
        yield client


def test_valid_request_returns_accepted_and_publishes_shared_event(
    ingestion_client: TestClient, queue: RecordingQueue
) -> None:
    response = ingestion_client.post("/api/v1/logs", json=payload())
    assert response.status_code == 202
    assert response.json() == {"status": "accepted", "event_id": str(EVENT_ID)}
    assert len(queue.events) == 1
    assert queue.events[0].event_id == EVENT_ID


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("level", "notice"),
        ("timestamp", "2026-07-22T12:00:00"),
        ("latency_ms", -1),
        ("status_code", 99),
        ("status_code", 600),
    ],
)
def test_invalid_inputs_return_422(
    ingestion_client: TestClient, field: str, value: object
) -> None:
    body = payload()
    body[field] = value
    assert ingestion_client.post("/api/v1/logs", json=body).status_code == 422


def test_missing_required_field_returns_422(ingestion_client: TestClient) -> None:
    body = payload()
    del body["message"]
    assert ingestion_client.post("/api/v1/logs", json=body).status_code == 422


def test_received_at_is_forbidden(ingestion_client: TestClient) -> None:
    body = payload()
    body["received_at"] = "2026-07-22T12:00:00Z"
    response = ingestion_client.post("/api/v1/logs", json=body)
    assert response.status_code == 422
    assert response.json()["detail"][0]["type"] == "extra_forbidden"


def test_queue_full_returns_stable_503(test_settings: Settings) -> None:
    with TestClient(
        create_app(
            test_settings,
            event_queue=RecordingQueue(full=True),
            clock=FixedClock(),
            event_id_factory=lambda: EVENT_ID,
            event_processor=LoggingEventProcessor(),
        )
    ) as client:
        response = client.post("/api/v1/logs", json=payload())
    assert response.status_code == 503
    assert response.json() == {
        "detail": "Log ingestion capacity is temporarily unavailable."
    }


class BrokenService:
    async def ingest(self, data: object) -> object:
        raise RuntimeError("unexpected")


def test_unexpected_service_error_remains_500(test_settings: Settings) -> None:
    application = create_app(
        test_settings,
        event_queue=RecordingQueue(),
        event_processor=LoggingEventProcessor(),
    )
    application.dependency_overrides[get_ingestion_service] = BrokenService
    with TestClient(application, raise_server_exceptions=False) as client:
        response = client.post("/api/v1/logs", json=payload())
    assert response.status_code == 500
