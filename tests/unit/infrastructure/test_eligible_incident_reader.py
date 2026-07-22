"""Tests for eligible incident finding mapping and SQL shape."""

from datetime import UTC, datetime
from uuid import UUID

import pytest

from app.infrastructure.database.eligible_incident_reader import (
    EligibleIncidentFindingMappingError,
    map_eligible_incident_finding,
)
from app.infrastructure.database.models import AnomalyFindingRecord, LogEventRecord

NOW = datetime(2026, 7, 22, 12, tzinfo=UTC)


def records() -> tuple[AnomalyFindingRecord, LogEventRecord]:
    event = LogEventRecord(
        event_id=UUID(int=1),
        timestamp=NOW,
        received_at=NOW,
        service="payments",
        environment="prod",
        level="ERROR",
        message="private",
        exception_type=None,
        exception_message=None,
        latency_ms=None,
        status_code=None,
        trace_id=None,
        request_id=None,
        host=None,
        event_metadata={"private": True},
    )
    finding = AnomalyFindingRecord(
        id=UUID(int=2),
        event_id=event.event_id,
        anomaly_type="high_latency",
        severity="high",
        rule_id="rule.v1",
        title="Latency",
        evidence=["safe"],
        created_at=NOW,
    )
    return finding, event


def test_mapping_preserves_safe_fields_only() -> None:
    finding, event = records()
    value = map_eligible_incident_finding(finding, event)
    assert (
        value.finding.id == finding.id
        and value.service == "payments"
        and value.event_timestamp == NOW
    )
    assert (
        value.finding.evidence == ("safe",)
        and not hasattr(value, "message")
        and not hasattr(value, "metadata")
    )


def test_mapping_rejects_mismatch_unknown_enum_and_naive_time() -> None:
    finding, event = records()
    finding.event_id = UUID(int=99)
    with pytest.raises(EligibleIncidentFindingMappingError):
        map_eligible_incident_finding(finding, event)
    finding, event = records()
    finding.anomaly_type = "unknown"
    with pytest.raises(EligibleIncidentFindingMappingError):
        map_eligible_incident_finding(finding, event)
    finding, event = records()
    event.timestamp = NOW.replace(tzinfo=None)
    with pytest.raises(EligibleIncidentFindingMappingError):
        map_eligible_incident_finding(finding, event)
