"""Immutable incident grouping keys and candidate values."""

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from app.domain.anomalies import AnomalySeverity, AnomalyType
from app.domain.logs.models import ENVIRONMENT_MAX_LENGTH, SERVICE_MAX_LENGTH


def _bounded(value: str, *, name: str, maximum: int) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{name} must be a string")
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{name} must not be blank")
    if len(normalized) > maximum:
        raise ValueError(f"{name} must be at most {maximum} characters")
    return normalized


def _utc(value: datetime, *, name: str) -> datetime:
    if not isinstance(value, datetime):
        raise TypeError(f"{name} must be a datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")
    return value.astimezone(UTC)


@dataclass(frozen=True, slots=True)
class IncidentGroupingKey:
    service: str
    environment: str
    anomaly_type: AnomalyType

    def __post_init__(self) -> None:
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
        if not isinstance(self.anomaly_type, AnomalyType):
            raise TypeError("anomaly_type must be an AnomalyType")


@dataclass(frozen=True, slots=True)
class IncidentCandidate:
    key: IncidentGroupingKey
    finding_ids: tuple[UUID, ...]
    event_ids: tuple[UUID, ...]
    rule_ids: tuple[str, ...]
    started_at: datetime
    last_seen_at: datetime
    finding_count: int
    highest_severity: AnomalySeverity

    def __post_init__(self) -> None:
        if not isinstance(self.key, IncidentGroupingKey):
            raise TypeError("key must be an IncidentGroupingKey")
        if not all(
            isinstance(values, tuple)
            for values in (self.finding_ids, self.event_ids, self.rule_ids)
        ):
            raise TypeError("candidate identifiers must be tuples")
        if len(self.finding_ids) < 2:
            raise ValueError("incident candidate requires at least two findings")
        if not (
            len(self.finding_ids)
            == len(self.event_ids)
            == len(self.rule_ids)
            == self.finding_count
        ):
            raise ValueError("candidate tuples and finding_count must align")
        if not all(
            isinstance(value, UUID) for value in (*self.finding_ids, *self.event_ids)
        ):
            raise TypeError("finding and event IDs must be UUIDs")
        if not all(isinstance(value, str) and value.strip() for value in self.rule_ids):
            raise ValueError("rule IDs must be nonblank strings")
        object.__setattr__(self, "started_at", _utc(self.started_at, name="started_at"))
        object.__setattr__(
            self, "last_seen_at", _utc(self.last_seen_at, name="last_seen_at")
        )
        if self.started_at > self.last_seen_at:
            raise ValueError("started_at must not be later than last_seen_at")
        if not isinstance(self.highest_severity, AnomalySeverity):
            raise TypeError("highest_severity must be an AnomalySeverity")
