"""Tests for anomaly ORM mapping and schema metadata."""

from datetime import UTC, datetime
from typing import cast
from uuid import UUID

from sqlalchemy import DateTime, String, Table, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID

from app.domain.anomalies import AnomalyFinding, AnomalySeverity, AnomalyType
from app.domain.anomalies.models import RULE_ID_MAX_LENGTH, TITLE_MAX_LENGTH
from app.infrastructure.database.mapper import map_anomaly_finding
from app.infrastructure.database.models import (
    ANOMALY_SEVERITY_MAX_LENGTH,
    ANOMALY_TYPE_MAX_LENGTH,
    AnomalyFindingRecord,
)


def finding() -> AnomalyFinding:
    return AnomalyFinding(
        AnomalyType.SERVER_ERROR_STATUS,
        AnomalySeverity.CRITICAL,
        "single_event.server_error_status.v1",
        "Server error response",
        ("status_code=575", "threshold_status=500"),
    )


def test_complete_finding_mapping_is_explicit_json_safe_and_non_mutating() -> None:
    event_id = UUID(int=9)
    persistence_id = UUID(int=91)
    created_at = datetime(2026, 7, 22, 12, tzinfo=UTC)
    value = finding()
    before = value.evidence
    record = map_anomaly_finding(
        event_id, value, created_at, persistence_id=persistence_id
    )
    assert record.id == persistence_id and record.event_id == event_id
    assert record.anomaly_type == "server_error_status"
    assert record.severity == "critical"
    assert record.rule_id == value.rule_id and record.title == value.title
    assert record.evidence == list(value.evidence) and isinstance(record.evidence, list)
    assert record.created_at is created_at and value.evidence == before
    assert not hasattr(record, "message")
    assert "metadata" not in record.__table__.c


def test_default_mapping_assigns_distinct_storage_ids() -> None:
    first = map_anomaly_finding(UUID(int=1), finding(), datetime.now(UTC))
    second = map_anomaly_finding(UUID(int=1), finding(), datetime.now(UTC))
    assert first.id != second.id


def test_anomaly_table_types_constraints_indexes_and_nullability() -> None:
    table = cast(Table, AnomalyFindingRecord.__table__)
    assert table.name == "anomaly_findings"
    assert isinstance(table.c.id.type, PG_UUID) and table.c.id.type.as_uuid
    assert isinstance(table.c.event_id.type, PG_UUID) and table.c.event_id.type.as_uuid
    assert isinstance(table.c.evidence.type, JSONB)
    assert (
        isinstance(table.c.created_at.type, DateTime)
        and table.c.created_at.type.timezone
    )
    assert all(not column.nullable for column in table.c)
    assert isinstance(table.c.anomaly_type.type, String)
    assert table.c.anomaly_type.type.length == ANOMALY_TYPE_MAX_LENGTH
    assert cast(String, table.c.severity.type).length == ANOMALY_SEVERITY_MAX_LENGTH
    assert cast(String, table.c.rule_id.type).length == RULE_ID_MAX_LENGTH
    assert cast(String, table.c.title.type).length == TITLE_MAX_LENGTH
    foreign_key = next(iter(table.c.event_id.foreign_keys))
    assert foreign_key.target_fullname == "log_events.event_id"
    assert foreign_key.ondelete == "CASCADE"
    assert {index.name for index in table.indexes} == {
        "ix_anomaly_findings_event_id",
        "ix_anomaly_findings_severity",
        "ix_anomaly_findings_anomaly_type",
        "ix_anomaly_findings_created_at",
    }
    unique = [item for item in table.constraints if isinstance(item, UniqueConstraint)]
    assert len(unique) == 1
    assert unique[0].name == "uq_anomaly_findings_event_rule"
    assert [column.name for column in unique[0].columns] == ["event_id", "rule_id"]
