from datetime import UTC, datetime
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from app.application.services.ingestion import IngestionService
from app.presentation.api.main import create_app
from app.shared.config import Settings

EVENT_ID = UUID("12345678-1234-5678-1234-567812345678")


class FixedClock:
    def now(self) -> datetime:
        return datetime(2026, 7, 22, 12, tzinfo=UTC)


def payload() -> dict[str, object]:
    return {
        "timestamp": "2026-07-22T13:00:00+01:00",
        "service": "api",
        "environment": "test",
        "level": "warn",
        "message": "slow",
    }


@pytest.fixture
def ingestion_client(test_settings: Settings) -> TestClient:
    return TestClient(
        create_app(test_settings, IngestionService(FixedClock(), lambda: EVENT_ID))
    )


def test_valid_request_returns_accepted_with_injected_uuid(
    ingestion_client: TestClient,
) -> None:
    response = ingestion_client.post("/api/v1/logs", json=payload())
    assert response.status_code == 202
    assert response.json() == {"status": "accepted", "event_id": str(EVENT_ID)}


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
