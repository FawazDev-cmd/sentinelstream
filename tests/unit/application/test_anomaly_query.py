"""Tests for persisted anomaly query values and cursor codec."""

import base64
import json
from dataclasses import FrozenInstanceError
from datetime import UTC, datetime, timedelta
from typing import Any, cast
from uuid import UUID

import pytest

from app.application.queries.anomalies import (
    AnomalyFindingCursor,
    AnomalyFindingPage,
    AnomalyFindingQuery,
    PersistedAnomalyFinding,
)
from app.application.queries.anomaly_cursor import (
    InvalidAnomalyFindingCursorError,
    decode_anomaly_finding_cursor,
    encode_anomaly_finding_cursor,
)
from app.domain.anomalies import AnomalySeverity, AnomalyType
from app.domain.anomalies.models import RULE_ID_MAX_LENGTH

MOMENT = datetime(2026, 7, 22, 12, tzinfo=UTC)


def persisted() -> PersistedAnomalyFinding:
    return PersistedAnomalyFinding(
        UUID(int=10),
        UUID(int=20),
        AnomalyType.HIGH_LATENCY,
        AnomalySeverity.CRITICAL,
        "single_event.high_latency.v1",
        "High request latency",
        ("latency_ms=6000",),
        MOMENT,
    )


def test_persisted_model_and_page_are_immutable_and_preserve_values() -> None:
    value = persisted()
    assert value.id == UUID(int=10) and value.event_id == UUID(int=20)
    assert value.anomaly_type is AnomalyType.HIGH_LATENCY
    assert value.severity is AnomalySeverity.CRITICAL
    assert value.evidence == ("latency_ms=6000",)
    with pytest.raises(FrozenInstanceError):
        value.title = "changed"  # type: ignore[misc]
    with pytest.raises(TypeError):
        PersistedAnomalyFinding(
            UUID(int=1),
            UUID(int=2),
            AnomalyType.ERROR_LEVEL,
            AnomalySeverity.HIGH,
            "rule",
            "title",
            cast(Any, ["mutable"]),
            MOMENT,
        )
    with pytest.raises(ValueError, match="timezone-aware"):
        PersistedAnomalyFinding(
            UUID(int=1),
            UUID(int=2),
            AnomalyType.ERROR_LEVEL,
            AnomalySeverity.HIGH,
            "rule",
            "title",
            ("safe",),
            datetime(2026, 1, 1),
        )
    page = AnomalyFindingPage((value,))
    with pytest.raises(FrozenInstanceError):
        page.items = ()  # type: ignore[misc]


def test_query_defaults_bounds_combination_utc_and_immutability() -> None:
    assert AnomalyFindingQuery().limit == 50
    assert AnomalyFindingQuery(limit=1).limit == 1
    assert AnomalyFindingQuery(limit=100).limit == 100
    offset = timezone = UTC
    query = AnomalyFindingQuery(
        event_id=UUID(int=2),
        anomaly_type=AnomalyType.ERROR_LEVEL,
        severity=AnomalySeverity.HIGH,
        rule_id="rule.v1",
        start_time=MOMENT.astimezone(offset),
        end_time=MOMENT + timedelta(hours=1),
        limit=25,
        cursor=AnomalyFindingCursor(MOMENT, UUID(int=3)),
    )
    assert query.start_time == MOMENT and timezone is UTC
    with pytest.raises(FrozenInstanceError):
        query.limit = 10  # type: ignore[misc]


@pytest.mark.parametrize(
    "kwargs",
    [
        {"limit": 0},
        {"limit": 101},
        {"rule_id": " "},
        {"rule_id": "x" * (RULE_ID_MAX_LENGTH + 1)},
        {"start_time": datetime(2026, 1, 1)},
        {"end_time": datetime(2026, 1, 1)},
        {"start_time": MOMENT + timedelta(seconds=1), "end_time": MOMENT},
    ],
)
def test_query_rejects_invalid_criteria_without_clamping(
    kwargs: dict[str, object],
) -> None:
    with pytest.raises((TypeError, ValueError)):
        AnomalyFindingQuery(**kwargs)  # type: ignore[arg-type]


def token(payload: object) -> str:
    raw = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def test_cursor_encoding_is_deterministic_canonical_url_safe_and_reversible() -> None:
    cursor = AnomalyFindingCursor(MOMENT, UUID(int=4))
    encoded = encode_anomaly_finding_cursor(cursor)
    assert encoded == encode_anomaly_finding_cursor(cursor)
    assert "=" not in encoded and all(
        character.isalnum() or character in "-_" for character in encoded
    )
    decoded_json = base64.urlsafe_b64decode(
        encoded + "=" * (-len(encoded) % 4)
    ).decode()
    assert '"created_at":"2026-07-22T12:00:00Z"' in decoded_json
    assert decode_anomaly_finding_cursor(encoded) == cursor
    with pytest.raises(FrozenInstanceError):
        cursor.finding_id = UUID(int=5)  # type: ignore[misc]


@pytest.mark.parametrize(
    "value",
    [
        "%%%",
        base64.urlsafe_b64encode(b"\xff").decode().rstrip("="),
        base64.urlsafe_b64encode(b"not-json").decode().rstrip("="),
        token([]),
        token({"created_at": "2026-07-22T12:00:00Z"}),
        token(
            {"created_at": "2026-07-22T12:00:00Z", "id": str(UUID(int=1)), "extra": "x"}
        ),
        token({"created_at": 1, "id": str(UUID(int=1))}),
        token({"created_at": "2026-07-22T12:00:00Z", "id": "bad"}),
        token({"created_at": "bad", "id": str(UUID(int=1))}),
        token({"created_at": "2026-07-22T12:00:00", "id": str(UUID(int=1))}),
    ],
)
def test_cursor_strictly_rejects_malformed_values(value: str) -> None:
    with pytest.raises(InvalidAnomalyFindingCursorError):
        decode_anomaly_finding_cursor(value)
