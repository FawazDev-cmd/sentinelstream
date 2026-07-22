"""Deterministic UUIDv5 identity for immutable incident candidates."""

from uuid import UUID, uuid5

from app.domain.incidents import IncidentCandidate

INCIDENT_ID_NAMESPACE = UUID("d29a2bc9-f7c5-5d89-bc6f-8729078e5a12")


def _canonical_utc(value: object) -> str:
    from datetime import datetime

    if not isinstance(value, datetime):
        raise TypeError("incident occurrence bound must be a datetime")
    return value.isoformat().replace("+00:00", "Z")


def build_incident_id(candidate: IncidentCandidate) -> UUID:
    service = candidate.key.service
    environment = candidate.key.environment
    name = "\n".join(
        (
            "version=1",
            f"service={len(service)}:{service}",
            f"environment={len(environment)}:{environment}",
            f"anomaly_type={candidate.key.anomaly_type.value}",
            f"started_at={_canonical_utc(candidate.started_at)}",
            f"last_seen_at={_canonical_utc(candidate.last_seen_at)}",
            "finding_ids=" + ",".join(str(value) for value in candidate.finding_ids),
        )
    )
    return uuid5(INCIDENT_ID_NAMESPACE, name)
