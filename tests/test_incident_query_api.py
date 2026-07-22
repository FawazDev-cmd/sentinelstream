"""API tests for read-only incident retrieval."""

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from app.application.queries.incidents import (
    IncidentCursor,
    IncidentPage,
    IncidentQuery,
    PersistedIncident,
    PersistedIncidentDetail,
    PersistedIncidentFinding,
)
from app.application.services.processor import LoggingEventProcessor
from app.domain.anomalies import AnomalySeverity, AnomalyType
from app.presentation.api.main import create_app
from app.shared.config import Settings

NOW = datetime(2026, 7, 22, 12, tzinfo=UTC)


def summary(identity: int = 1) -> PersistedIncident:
    return PersistedIncident(
        UUID(int=identity),
        "payments",
        "prod",
        AnomalyType.HIGH_LATENCY,
        NOW,
        NOW + timedelta(minutes=identity),
        2,
        AnomalySeverity.CRITICAL,
        NOW,
    )


def detail() -> PersistedIncidentDetail:
    value = summary()
    findings = tuple(
        PersistedIncidentFinding(
            UUID(int=i + 10),
            UUID(int=i + 20),
            i,
            AnomalyType.HIGH_LATENCY,
            AnomalySeverity.HIGH,
            f"rule.{i}",
            "Latency",
            ("safe",),
            NOW,
        )
        for i in range(2)
    )
    return PersistedIncidentDetail(value, findings)


class FakeIncidentReader:
    def __init__(self) -> None:
        self.page = IncidentPage(())
        self.detail: PersistedIncidentDetail | None = None
        self.failure: Exception | None = None
        self.queries: list[IncidentQuery] = []

    async def list(self, query: IncidentQuery) -> IncidentPage:
        self.queries.append(query)
        if self.failure:
            raise self.failure
        return self.page

    async def get(self, incident_id: UUID) -> PersistedIncidentDetail | None:
        if self.failure:
            raise self.failure
        return self.detail


@pytest.fixture
def incident_api(
    test_settings: Settings,
) -> Iterator[tuple[TestClient, FakeIncidentReader]]:
    reader = FakeIncidentReader()
    with TestClient(
        create_app(
            test_settings,
            event_processor=LoggingEventProcessor(),
            incident_reader=reader,
        )
    ) as client:
        yield client, reader


def test_list_empty_filters_and_cursor(
    incident_api: tuple[TestClient, FakeIncidentReader],
) -> None:
    client, reader = incident_api
    assert client.get("/api/v1/incidents").json() == {"items": [], "next_cursor": None}
    reader.page = IncidentPage(
        (summary(),), IncidentCursor(summary().last_seen_at, summary().id)
    )
    response = client.get(
        "/api/v1/incidents",
        params={"service": "payments", "highest_severity": "critical", "limit": 2},
    )
    body = response.json()
    assert (
        response.status_code == 200 and len(body["items"]) == 1 and body["next_cursor"]
    )
    assert (
        "findings" not in body["items"][0]
        and "message" not in str(body)
        and "metadata" not in str(body)
    )
    assert reader.queries[-1].service == "payments" and reader.queries[-1].limit == 2


def test_detail_missing_invalid_and_safe_failures(
    incident_api: tuple[TestClient, FakeIncidentReader],
) -> None:
    client, reader = incident_api
    reader.detail = detail()
    response = client.get(f"/api/v1/incidents/{UUID(int=1)}")
    assert response.status_code == 200 and [
        item["position"] for item in response.json()["findings"]
    ] == [0, 1]
    reader.detail = None
    assert client.get(f"/api/v1/incidents/{UUID(int=99)}").status_code == 404
    assert client.get("/api/v1/incidents/not-a-uuid").status_code == 422
    assert client.get("/api/v1/incidents?cursor=invalid").status_code == 422
    reader.failure = RuntimeError("secret database detail")
    failed = client.get("/api/v1/incidents")
    assert failed.status_code == 500 and "secret" not in failed.text


def test_only_get_routes_are_registered(
    incident_api: tuple[TestClient, FakeIncidentReader],
) -> None:
    client, _ = incident_api
    paths = client.get("/openapi.json").json()["paths"]
    assert set(paths["/api/v1/incidents"]) == {"get"}
    assert set(paths["/api/v1/incidents/{incident_id}"]) == {"get"}
