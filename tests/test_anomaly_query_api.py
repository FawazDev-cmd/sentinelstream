"""API tests for persisted anomaly retrieval."""

from collections.abc import Iterator
from datetime import UTC, datetime
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from app.application.queries.anomalies import (
    AnomalyFindingCursor,
    AnomalyFindingPage,
    AnomalyFindingQuery,
    PersistedAnomalyFinding,
)
from app.application.queries.anomaly_cursor import encode_anomaly_finding_cursor
from app.application.services.processor import LoggingEventProcessor
from app.domain.anomalies import AnomalySeverity, AnomalyType
from app.presentation.api import main
from app.shared.config import Settings

MOMENT = datetime(2026, 7, 22, 12, tzinfo=UTC)


class FakeAnomalyReader:
    def __init__(
        self, page: AnomalyFindingPage | None = None, failure: Exception | None = None
    ) -> None:
        self.page = page or AnomalyFindingPage(())
        self.failure = failure
        self.queries: list[AnomalyFindingQuery] = []

    async def list(self, query: AnomalyFindingQuery) -> AnomalyFindingPage:
        self.queries.append(query)
        if self.failure is not None:
            raise self.failure
        return self.page


def item() -> PersistedAnomalyFinding:
    return PersistedAnomalyFinding(
        UUID(int=10),
        UUID(int=20),
        AnomalyType.HIGH_LATENCY,
        AnomalySeverity.CRITICAL,
        "single_event.high_latency.v1",
        "High request latency",
        ("latency_ms=6000", "threshold_ms=1000"),
        MOMENT,
    )


@pytest.fixture
def api(test_settings: Settings) -> Iterator[tuple[TestClient, FakeAnomalyReader]]:
    reader = FakeAnomalyReader()
    with TestClient(
        main.create_app(
            test_settings,
            event_processor=LoggingEventProcessor(),
            anomaly_finding_reader=reader,
        )
    ) as client:
        yield client, reader


def test_default_query_and_route_registered_once(
    api: tuple[TestClient, FakeAnomalyReader],
) -> None:
    client, reader = api
    response = client.get("/api/v1/anomalies")
    assert response.status_code == 200 and response.json() == {
        "items": [],
        "next_cursor": None,
    }
    assert reader.queries == [AnomalyFindingQuery()]
    operations = client.get("/openapi.json").json()["paths"]["/api/v1/anomalies"]
    assert set(operations) == {"get"}


def test_all_filters_cursor_and_typed_response(
    api: tuple[TestClient, FakeAnomalyReader],
) -> None:
    client, reader = api
    cursor = AnomalyFindingCursor(MOMENT, UUID(int=9))
    reader.page = AnomalyFindingPage((item(),), cursor)
    response = client.get(
        "/api/v1/anomalies",
        params={
            "event_id": str(UUID(int=20)),
            "anomaly_type": "high_latency",
            "severity": "critical",
            "rule_id": "single_event.high_latency.v1",
            "start_time": "2026-07-22T12:00:00Z",
            "end_time": "2026-07-22T13:00:00Z",
            "limit": 2,
            "cursor": encode_anomaly_finding_cursor(cursor),
        },
    )
    assert response.status_code == 200
    assert reader.queries == [
        AnomalyFindingQuery(
            event_id=UUID(int=20),
            anomaly_type=AnomalyType.HIGH_LATENCY,
            severity=AnomalySeverity.CRITICAL,
            rule_id="single_event.high_latency.v1",
            start_time=MOMENT,
            end_time=datetime(2026, 7, 22, 13, tzinfo=UTC),
            limit=2,
            cursor=cursor,
        )
    ]
    body = response.json()
    assert body["next_cursor"] == encode_anomaly_finding_cursor(cursor)
    assert body["items"][0] == {
        "id": str(UUID(int=10)),
        "event_id": str(UUID(int=20)),
        "anomaly_type": "high_latency",
        "severity": "critical",
        "rule_id": "single_event.high_latency.v1",
        "title": "High request latency",
        "evidence": ["latency_ms=6000", "threshold_ms=1000"],
        "created_at": "2026-07-22T12:00:00Z",
    }


@pytest.mark.parametrize(
    "params",
    [
        {"cursor": "invalid"},
        {"limit": 0},
        {"limit": 101},
        {"rule_id": " "},
        {"start_time": "2026-07-23T00:00:00Z", "end_time": "2026-07-22T00:00:00Z"},
        {"anomaly_type": "unknown"},
        {"severity": "urgent"},
    ],
)
def test_invalid_queries_return_422_without_reader_call(
    api: tuple[TestClient, FakeAnomalyReader], params: dict[str, object]
) -> None:
    response = api[0].get("/api/v1/anomalies", params=params)
    assert response.status_code == 422 and api[1].queries == []


def test_reader_failure_returns_safe_500(test_settings: Settings) -> None:
    reader = FakeAnomalyReader(
        failure=RuntimeError("postgresql://user:secret@host/db SQL")
    )
    app = main.create_app(
        test_settings,
        event_processor=LoggingEventProcessor(),
        anomaly_finding_reader=reader,
    )
    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get("/api/v1/anomalies")
    assert response.status_code == 500
    assert response.json() == {"detail": "Unable to retrieve anomaly findings."}
    assert "secret" not in response.text and "postgresql" not in response.text


def test_injected_reader_and_processor_bypass_database(
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
            anomaly_finding_reader=FakeAnomalyReader(),
        )
    ) as client:
        assert client.get("/api/v1/anomalies").status_code == 200
