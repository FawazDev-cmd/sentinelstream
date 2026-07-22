"""Explicit incident ORM-to-application read mapping."""

from app.application.queries.incidents import (
    PersistedIncident,
    PersistedIncidentDetail,
    PersistedIncidentFinding,
)
from app.domain.anomalies import AnomalySeverity, AnomalyType
from app.infrastructure.database.models import (
    AnomalyFindingRecord,
    IncidentFindingRecord,
    IncidentRecord,
)


class IncidentReadMappingError(ValueError):
    """Raised when persisted incident state violates read invariants."""


def map_incident_record(record: IncidentRecord) -> PersistedIncident:
    try:
        return PersistedIncident(
            id=record.id,
            service=record.service,
            environment=record.environment,
            anomaly_type=AnomalyType(record.anomaly_type),
            started_at=record.started_at,
            last_seen_at=record.last_seen_at,
            finding_count=record.finding_count,
            highest_severity=AnomalySeverity(record.highest_severity),
            created_at=record.created_at,
        )
    except (TypeError, ValueError) as error:
        raise IncidentReadMappingError(
            "Persisted incident state is invalid."
        ) from error


def map_incident_detail(
    incident_record: IncidentRecord,
    rows: list[tuple[IncidentFindingRecord, AnomalyFindingRecord]],
) -> PersistedIncidentDetail:
    try:
        incident = map_incident_record(incident_record)
        findings = tuple(
            PersistedIncidentFinding(
                finding_id=finding.id,
                event_id=finding.event_id,
                position=membership.position,
                anomaly_type=AnomalyType(finding.anomaly_type),
                severity=AnomalySeverity(finding.severity),
                rule_id=finding.rule_id,
                title=finding.title,
                evidence=tuple(finding.evidence),
                finding_created_at=finding.created_at,
            )
            for membership, finding in rows
            if membership.incident_id == incident.id
            and membership.finding_id == finding.id
        )
        if len(findings) != len(rows):
            raise ValueError("membership identity mismatch")
        return PersistedIncidentDetail(incident, findings)
    except (TypeError, ValueError) as error:
        if isinstance(error, IncidentReadMappingError):
            raise
        raise IncidentReadMappingError(
            "Persisted incident detail is invalid."
        ) from error
