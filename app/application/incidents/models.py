"""Immutable input and policy values for incident grouping."""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from app.application.queries.anomalies import PersistedAnomalyFinding
from app.domain.logs.models import ENVIRONMENT_MAX_LENGTH, SERVICE_MAX_LENGTH

MAXIMUM_MINIMUM_FINDINGS = 10_000


def _bounded(value: str, *, name: str, maximum: int) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{name} must be a string")
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{name} must not be blank")
    if len(normalized) > maximum:
        raise ValueError(f"{name} must be at most {maximum} characters")
    return normalized


@dataclass(frozen=True, slots=True)
class IncidentGroupingInput:
    finding: PersistedAnomalyFinding
    service: str
    environment: str
    event_timestamp: datetime

    def __post_init__(self) -> None:
        if not isinstance(self.finding, PersistedAnomalyFinding):
            raise TypeError("finding must be a PersistedAnomalyFinding")
        object.__setattr__(
            self,
            "service",
            _bounded(self.service, name="service", maximum=SERVICE_MAX_LENGTH),
        )
        object.__setattr__(
            self,
            "environment",
            _bounded(
                self.environment, name="environment", maximum=ENVIRONMENT_MAX_LENGTH
            ),
        )
        if not isinstance(self.event_timestamp, datetime):
            raise TypeError("event_timestamp must be a datetime")
        if (
            self.event_timestamp.tzinfo is None
            or self.event_timestamp.utcoffset() is None
        ):
            raise ValueError("event_timestamp must be timezone-aware")
        object.__setattr__(
            self, "event_timestamp", self.event_timestamp.astimezone(UTC)
        )


@dataclass(frozen=True, slots=True)
class IncidentGroupingPolicy:
    maximum_gap: timedelta = timedelta(minutes=5)
    minimum_findings: int = 2

    def __post_init__(self) -> None:
        if not isinstance(self.maximum_gap, timedelta):
            raise TypeError("maximum_gap must be a timedelta")
        if self.maximum_gap <= timedelta(0):
            raise ValueError("maximum_gap must be greater than zero")
        if isinstance(self.minimum_findings, bool) or not isinstance(
            self.minimum_findings, int
        ):
            raise TypeError("minimum_findings must be an integer")
        if not 2 <= self.minimum_findings <= MAXIMUM_MINIMUM_FINDINGS:
            raise ValueError(
                f"minimum_findings must be between 2 and {MAXIMUM_MINIMUM_FINDINGS}"
            )
