"""Typed read-only incident response schemas."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel

from app.application.queries.incidents import (
    PersistedIncident,
    PersistedIncidentDetail,
    PersistedIncidentFinding,
)
from app.domain.anomalies import AnomalySeverity, AnomalyType


class IncidentResponse(BaseModel):
    id: UUID
    service: str
    environment: str
    anomaly_type: AnomalyType
    started_at: datetime
    last_seen_at: datetime
    finding_count: int
    highest_severity: AnomalySeverity
    created_at: datetime

    @classmethod
    def from_incident(cls, value: PersistedIncident) -> "IncidentResponse":
        return cls(**{name: getattr(value, name) for name in cls.model_fields})


class IncidentFindingResponse(BaseModel):
    finding_id: UUID
    event_id: UUID
    position: int
    anomaly_type: AnomalyType
    severity: AnomalySeverity
    rule_id: str
    title: str
    evidence: list[str]
    created_at: datetime

    @classmethod
    def from_finding(cls, value: PersistedIncidentFinding) -> "IncidentFindingResponse":
        return cls(
            finding_id=value.finding_id,
            event_id=value.event_id,
            position=value.position,
            anomaly_type=value.anomaly_type,
            severity=value.severity,
            rule_id=value.rule_id,
            title=value.title,
            evidence=list(value.evidence),
            created_at=value.finding_created_at,
        )


class IncidentPageResponse(BaseModel):
    items: list[IncidentResponse]
    next_cursor: str | None


class IncidentDetailResponse(IncidentResponse):
    findings: list[IncidentFindingResponse]

    @classmethod
    def from_detail(cls, value: PersistedIncidentDetail) -> "IncidentDetailResponse":
        summary = IncidentResponse.from_incident(value.incident)
        return cls(
            **summary.model_dump(),
            findings=[
                IncidentFindingResponse.from_finding(item) for item in value.findings
            ],
        )
