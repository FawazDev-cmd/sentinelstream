"""Typed response schemas for persisted anomaly findings."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel

from app.application.queries.anomalies import PersistedAnomalyFinding
from app.domain.anomalies import AnomalySeverity, AnomalyType


class AnomalyFindingResponse(BaseModel):
    id: UUID
    event_id: UUID
    anomaly_type: AnomalyType
    severity: AnomalySeverity
    rule_id: str
    title: str
    evidence: list[str]
    created_at: datetime

    @classmethod
    def from_finding(cls, finding: PersistedAnomalyFinding) -> "AnomalyFindingResponse":
        return cls(
            id=finding.id,
            event_id=finding.event_id,
            anomaly_type=finding.anomaly_type,
            severity=finding.severity,
            rule_id=finding.rule_id,
            title=finding.title,
            evidence=list(finding.evidence),
            created_at=finding.created_at,
        )


class AnomalyFindingPageResponse(BaseModel):
    items: list[AnomalyFindingResponse]
    next_cursor: str | None
