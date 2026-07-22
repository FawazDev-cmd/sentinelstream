"""Immutable anomaly findings and per-event detection results."""

from dataclasses import dataclass
from uuid import UUID

from app.domain.anomalies.types import AnomalySeverity, AnomalyType

RULE_ID_MAX_LENGTH = 100
TITLE_MAX_LENGTH = 200
EVIDENCE_ITEM_MAX_LENGTH = 500
EVIDENCE_MAX_ITEMS = 20


def _validate_bounded_text(value: str, *, name: str, maximum: int) -> None:
    if not isinstance(value, str):
        raise TypeError(f"{name} must be a string")
    if not value.strip():
        raise ValueError(f"{name} must not be blank")
    if len(value) > maximum:
        raise ValueError(f"{name} must be at most {maximum} characters")


@dataclass(frozen=True, slots=True)
class AnomalyFinding:
    anomaly_type: AnomalyType
    severity: AnomalySeverity
    rule_id: str
    title: str
    evidence: tuple[str, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.anomaly_type, AnomalyType):
            raise TypeError("anomaly_type must be an AnomalyType")
        if not isinstance(self.severity, AnomalySeverity):
            raise TypeError("severity must be an AnomalySeverity")
        _validate_bounded_text(self.rule_id, name="rule_id", maximum=RULE_ID_MAX_LENGTH)
        _validate_bounded_text(self.title, name="title", maximum=TITLE_MAX_LENGTH)
        if not isinstance(self.evidence, tuple):
            raise TypeError("evidence must be a tuple")
        if not self.evidence:
            raise ValueError("evidence must contain at least one item")
        if len(self.evidence) > EVIDENCE_MAX_ITEMS:
            raise ValueError(
                f"evidence must contain at most {EVIDENCE_MAX_ITEMS} items"
            )
        for item in self.evidence:
            _validate_bounded_text(
                item, name="evidence item", maximum=EVIDENCE_ITEM_MAX_LENGTH
            )


@dataclass(frozen=True, slots=True)
class DetectionResult:
    event_id: UUID
    findings: tuple[AnomalyFinding, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.event_id, UUID):
            raise TypeError("event_id must be a UUID")
        if not isinstance(self.findings, tuple):
            raise TypeError("findings must be a tuple")
        if not all(isinstance(item, AnomalyFinding) for item in self.findings):
            raise TypeError("findings must contain only AnomalyFinding values")

    @property
    def is_anomalous(self) -> bool:
        return bool(self.findings)

    @property
    def highest_severity(self) -> AnomalySeverity | None:
        if not self.findings:
            return None
        return max(
            (finding.severity for finding in self.findings),
            key=lambda severity: severity.rank,
        )
