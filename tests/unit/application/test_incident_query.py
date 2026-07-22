"""Tests for incident read values and strict cursors."""

from dataclasses import FrozenInstanceError, replace
from datetime import UTC, datetime, timedelta, timezone
from uuid import UUID

import pytest

from app.application.queries.incident_cursor import (
    InvalidIncidentCursorError,
    decode_incident_cursor,
    encode_incident_cursor,
)
from app.application.queries.incidents import (
    IncidentCursor,
    IncidentQuery,
    PersistedIncident,
    PersistedIncidentDetail,
    PersistedIncidentFinding,
)
from app.domain.anomalies import AnomalySeverity, AnomalyType

NOW = datetime(2026, 7, 22, 12, tzinfo=UTC)


def incident(**changes: object) -> PersistedIncident:
    values = dict(
        id=UUID(int=1),
        service="payments",
        environment="prod",
        anomaly_type=AnomalyType.HIGH_LATENCY,
        started_at=NOW,
        last_seen_at=NOW + timedelta(minutes=1),
        finding_count=2,
        highest_severity=AnomalySeverity.CRITICAL,
        created_at=NOW,
    )
    values.update(changes)
    return PersistedIncident(**values)  # type: ignore[arg-type]


def finding(position: int, finding_id: int) -> PersistedIncidentFinding:
    return PersistedIncidentFinding(
        UUID(int=finding_id),
        UUID(int=100 + finding_id),
        position,
        AnomalyType.HIGH_LATENCY,
        AnomalySeverity.HIGH,
        "rule.v1",
        "Latency",
        ("safe evidence",),
        NOW,
    )


def test_summary_normalizes_and_validates() -> None:
    offset = timezone(timedelta(hours=2))
    value = incident(
        started_at=NOW.astimezone(offset),
        last_seen_at=(NOW + timedelta(minutes=1)).astimezone(offset),
    )
    assert value.id == UUID(int=1) and value.started_at.tzinfo is UTC
    with pytest.raises(ValueError):
        incident(started_at=NOW.replace(tzinfo=None))
    with pytest.raises(ValueError):
        incident(finding_count=1)
    with pytest.raises(ValueError):
        incident(started_at=NOW + timedelta(hours=2))
    with pytest.raises(FrozenInstanceError):
        value.service = "other"  # type: ignore[misc]
    assert not hasattr(value, "status") and not hasattr(value, "acknowledged")


def test_finding_and_detail_invariants() -> None:
    first, second = finding(0, 1), finding(1, 2)
    detail = PersistedIncidentDetail(incident(), (first, second))
    assert detail.findings == (first, second) and first.event_id == UUID(int=101)
    with pytest.raises(ValueError):
        replace(first, position=-1)
    with pytest.raises(ValueError):
        PersistedIncidentDetail(incident(), (first,))
    with pytest.raises(ValueError):
        PersistedIncidentDetail(incident(), (replace(first, position=1), second))
    with pytest.raises(ValueError):
        PersistedIncidentDetail(
            incident(), (first, replace(second, finding_id=first.finding_id))
        )


def test_query_validation_and_normalization() -> None:
    assert IncidentQuery().limit == 50
    assert IncidentQuery(limit=1).limit == 1 and IncidentQuery(limit=100).limit == 100
    for invalid in (0, 101):
        with pytest.raises(ValueError):
            IncidentQuery(limit=invalid)
    for values in (
        {"service": " "},
        {"environment": " "},
        {"minimum_finding_count": 1},
        {"started_after": NOW, "started_before": NOW - timedelta(seconds=1)},
        {"last_seen_after": NOW, "last_seen_before": NOW - timedelta(seconds=1)},
    ):
        with pytest.raises(ValueError):
            IncidentQuery(**values)
    assert (
        IncidentQuery(
            started_after=NOW.astimezone(timezone(timedelta(hours=2)))
        ).started_after
        == NOW
    )


def test_cursor_round_trip_is_strict_and_safe() -> None:
    cursor = IncidentCursor(NOW, UUID(int=9))
    token = encode_incident_cursor(cursor)
    assert decode_incident_cursor(token) == cursor and "=" not in token
    assert encode_incident_cursor(cursor) == token
    for invalid in ("invalid", token + "=", "", "e30"):
        with pytest.raises(InvalidIncidentCursorError) as caught:
            decode_incident_cursor(invalid)
        if invalid:
            assert invalid not in str(caught.value)
    with pytest.raises(ValueError):
        IncidentCursor(NOW.replace(tzinfo=None), UUID(int=1))
