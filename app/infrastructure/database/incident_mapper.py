"""Explicit incident candidate to ORM record mapping."""

from datetime import datetime
from uuid import UUID

from app.domain.incidents import IncidentCandidate
from app.infrastructure.database.models import IncidentFindingRecord, IncidentRecord


def map_incident_candidate(
    candidate: IncidentCandidate,
    incident_id: UUID,
    created_at: datetime,
) -> tuple[IncidentRecord, tuple[IncidentFindingRecord, ...]]:
    incident = IncidentRecord(
        id=incident_id,
        service=candidate.key.service,
        environment=candidate.key.environment,
        anomaly_type=candidate.key.anomaly_type.value,
        started_at=candidate.started_at,
        last_seen_at=candidate.last_seen_at,
        finding_count=candidate.finding_count,
        highest_severity=candidate.highest_severity.value,
        created_at=created_at,
    )
    memberships = tuple(
        IncidentFindingRecord(
            incident_id=incident_id,
            finding_id=finding_id,
            position=position,
            created_at=created_at,
        )
        for position, finding_id in enumerate(candidate.finding_ids)
    )
    return incident, memberships
