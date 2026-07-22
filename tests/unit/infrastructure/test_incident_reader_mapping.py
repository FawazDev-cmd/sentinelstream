"""Tests for explicit incident read mapping."""

from datetime import UTC, datetime
from uuid import UUID

import pytest

from app.domain.anomalies import AnomalySeverity, AnomalyType
from app.infrastructure.database.incident_read_mapper import (
    IncidentReadMappingError,
    map_incident_detail,
    map_incident_record,
)
from app.infrastructure.database.models import (
    AnomalyFindingRecord,
    IncidentFindingRecord,
    IncidentRecord,
)

NOW = datetime(2026, 7, 22, 12, tzinfo=UTC)


def records() -> tuple[
    IncidentRecord, list[tuple[IncidentFindingRecord, AnomalyFindingRecord]]
]:
    incident = IncidentRecord(
        id=UUID(int=10),
        service="payments",
        environment="prod",
        anomaly_type="high_latency",
        started_at=NOW,
        last_seen_at=NOW,
        finding_count=2,
        highest_severity="critical",
        created_at=NOW,
    )
    rows = []
    for position in range(2):
        finding_id = UUID(int=position + 1)
        rows.append(
            (
                IncidentFindingRecord(
                    incident_id=incident.id,
                    finding_id=finding_id,
                    position=position,
                    created_at=NOW,
                ),
                AnomalyFindingRecord(
                    id=finding_id,
                    event_id=UUID(int=100 + position),
                    anomaly_type="high_latency",
                    severity="high",
                    rule_id=f"rule.{position}",
                    title="Latency",
                    evidence=["safe"],
                    created_at=NOW,
                ),
            )
        )
    return incident, rows


def test_summary_and_detail_map_explicitly() -> None:
    record, rows = records()
    summary = map_incident_record(record)
    detail = map_incident_detail(record, rows)
    assert summary.anomaly_type is AnomalyType.HIGH_LATENCY
    assert summary.highest_severity is AnomalySeverity.CRITICAL
    assert [item.position for item in detail.findings] == [0, 1]
    assert detail.findings[0].evidence == ("safe",)
    assert not hasattr(detail.findings[0], "message") and not hasattr(
        detail.findings[0], "metadata"
    )


def test_mapping_rejects_malformed_state() -> None:
    record, rows = records()
    record.anomaly_type = "unknown"
    with pytest.raises(IncidentReadMappingError):
        map_incident_record(record)
    record, rows = records()
    rows.pop()
    with pytest.raises(IncidentReadMappingError):
        map_incident_detail(record, rows)
