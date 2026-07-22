"""Tests for incident ORM metadata and explicit mapping."""

from datetime import UTC, datetime
from typing import cast
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, String, Table, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PG_UUID

from app.application.incidents.identity import build_incident_id
from app.infrastructure.database.incident_mapper import map_incident_candidate
from app.infrastructure.database.models import IncidentFindingRecord, IncidentRecord
from tests.unit.application.incidents.test_identity import candidate


def test_incident_table_metadata_constraints_indexes_and_no_status() -> None:
    table = cast(Table, IncidentRecord.__table__)
    assert table.name == "incidents"
    assert isinstance(table.c.id.type, PG_UUID) and table.c.id.primary_key
    assert all(not column.nullable for column in table.c)
    for name in ("started_at", "last_seen_at", "created_at"):
        assert isinstance(table.c[name].type, DateTime)
        assert cast(DateTime, table.c[name].type).timezone
    for name in ("anomaly_type", "highest_severity"):
        assert isinstance(table.c[name].type, String)
        assert cast(String, table.c[name].type).length is not None
    assert {
        constraint.name
        for constraint in table.constraints
        if isinstance(constraint, CheckConstraint)
    } == {"ck_incidents_finding_count", "ck_incidents_occurrence_range"}
    assert {index.name for index in table.indexes} == {
        "ix_incidents_started_at",
        "ix_incidents_last_seen_at",
        "ix_incidents_highest_severity",
        "ix_incidents_service",
        "ix_incidents_environment",
        "ix_incidents_anomaly_type",
    }
    assert "acknowledged" not in table.c and "resolved" not in table.c


def test_membership_metadata_foreign_keys_uniqueness_and_no_copied_fields() -> None:
    table = cast(Table, IncidentFindingRecord.__table__)
    assert table.name == "incident_findings"
    assert set(table.primary_key.columns.keys()) == {"incident_id", "finding_id"}
    foreign_keys = {key.parent.name: key for key in table.foreign_keys}
    assert foreign_keys["incident_id"].target_fullname == "incidents.id"
    assert foreign_keys["incident_id"].ondelete == "CASCADE"
    assert foreign_keys["finding_id"].target_fullname == "anomaly_findings.id"
    assert foreign_keys["finding_id"].ondelete == "RESTRICT"
    unique = {
        constraint.name
        for constraint in table.constraints
        if isinstance(constraint, UniqueConstraint)
    }
    assert unique == {
        "uq_incident_findings_finding",
        "uq_incident_findings_incident_position",
    }
    assert {
        constraint.name
        for constraint in table.constraints
        if isinstance(constraint, CheckConstraint)
    } == {"ck_incident_findings_position"}
    assert set(table.c.keys()) == {
        "incident_id",
        "finding_id",
        "position",
        "created_at",
    }


def test_mapping_preserves_candidate_and_zero_based_membership_order() -> None:
    value = candidate()
    before = value
    incident_id = build_incident_id(value)
    created_at = datetime(2026, 7, 22, 13, tzinfo=UTC)
    incident, memberships = map_incident_candidate(value, incident_id, created_at)
    assert incident.id == incident_id
    assert (incident.service, incident.environment, incident.anomaly_type) == (
        "payments",
        "production",
        "high_latency",
    )
    assert (
        incident.started_at == value.started_at
        and incident.last_seen_at == value.last_seen_at
    )
    assert incident.finding_count == 2 and incident.highest_severity == "high"
    assert [(row.finding_id, row.position) for row in memberships] == [
        (UUID(int=1), 0),
        (UUID(int=2), 1),
    ]
    assert all(
        row.incident_id == incident_id and row.created_at == created_at
        for row in memberships
    )
    assert not hasattr(memberships[0], "event_id") and not hasattr(
        memberships[0], "rule_id"
    )
    assert value == before
    repeated = map_incident_candidate(value, incident_id, created_at)
    assert repeated[0].id == incident.id
    assert [(row.finding_id, row.position) for row in repeated[1]] == [
        (UUID(int=1), 0),
        (UUID(int=2), 1),
    ]
