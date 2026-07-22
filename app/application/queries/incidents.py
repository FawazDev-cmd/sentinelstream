"""Framework-independent persisted-incident query values."""

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from app.domain.anomalies import AnomalySeverity, AnomalyType
from app.domain.logs.models import ENVIRONMENT_MAX_LENGTH, SERVICE_MAX_LENGTH

DEFAULT_INCIDENT_QUERY_LIMIT = 50
MIN_INCIDENT_QUERY_LIMIT = 1
MAX_INCIDENT_QUERY_LIMIT = 100
MAXIMUM_INCIDENT_FINDING_COUNT = 10_000


def _aware_utc(value: datetime, *, field_name: str) -> datetime:
    if not isinstance(value, datetime):
        raise TypeError(f"{field_name} must be a datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
    return value.astimezone(UTC)


def _optional_bounded(value: str | None, *, name: str, maximum: int) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise TypeError(f"{name} must be a string")
    if not value.strip():
        raise ValueError(f"{name} must not be blank")
    if len(value) > maximum:
        raise ValueError(f"{name} must be at most {maximum} characters")
    return value


@dataclass(frozen=True, slots=True)
class PersistedIncident:
    id: UUID
    service: str
    environment: str
    anomaly_type: AnomalyType
    started_at: datetime
    last_seen_at: datetime
    finding_count: int
    highest_severity: AnomalySeverity
    created_at: datetime

    def __post_init__(self) -> None:
        if not isinstance(self.id, UUID):
            raise TypeError("incident id must be a UUID")
        if not isinstance(self.anomaly_type, AnomalyType):
            raise TypeError("anomaly_type must be an AnomalyType")
        if not isinstance(self.highest_severity, AnomalySeverity):
            raise TypeError("highest_severity must be an AnomalySeverity")
        if self.finding_count < 2:
            raise ValueError("finding_count must be at least two")
        object.__setattr__(
            self, "started_at", _aware_utc(self.started_at, field_name="started_at")
        )
        object.__setattr__(
            self,
            "last_seen_at",
            _aware_utc(self.last_seen_at, field_name="last_seen_at"),
        )
        object.__setattr__(
            self, "created_at", _aware_utc(self.created_at, field_name="created_at")
        )
        if self.started_at > self.last_seen_at:
            raise ValueError("started_at must not be later than last_seen_at")


@dataclass(frozen=True, slots=True)
class PersistedIncidentFinding:
    finding_id: UUID
    event_id: UUID
    position: int
    anomaly_type: AnomalyType
    severity: AnomalySeverity
    rule_id: str
    title: str
    evidence: tuple[str, ...]
    finding_created_at: datetime

    def __post_init__(self) -> None:
        if not isinstance(self.finding_id, UUID) or not isinstance(self.event_id, UUID):
            raise TypeError("finding and event IDs must be UUIDs")
        if isinstance(self.position, bool) or not isinstance(self.position, int):
            raise TypeError("position must be an integer")
        if self.position < 0:
            raise ValueError("position must be nonnegative")
        if not isinstance(self.anomaly_type, AnomalyType) or not isinstance(
            self.severity, AnomalySeverity
        ):
            raise TypeError("finding enums are invalid")
        if not isinstance(self.evidence, tuple) or not all(
            isinstance(item, str) for item in self.evidence
        ):
            raise TypeError("evidence must be a tuple of strings")
        object.__setattr__(
            self,
            "finding_created_at",
            _aware_utc(self.finding_created_at, field_name="finding_created_at"),
        )


@dataclass(frozen=True, slots=True)
class PersistedIncidentDetail:
    incident: PersistedIncident
    findings: tuple[PersistedIncidentFinding, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.findings, tuple):
            raise TypeError("findings must be a tuple")
        if len(self.findings) != self.incident.finding_count:
            raise ValueError("finding count does not match incident")
        positions = tuple(item.position for item in self.findings)
        if positions != tuple(range(self.incident.finding_count)):
            raise ValueError("finding positions must be contiguous and zero-based")
        ids = tuple(item.finding_id for item in self.findings)
        if len(set(ids)) != len(ids):
            raise ValueError("finding IDs must be unique")


@dataclass(frozen=True, slots=True)
class IncidentCursor:
    last_seen_at: datetime
    incident_id: UUID

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "last_seen_at",
            _aware_utc(self.last_seen_at, field_name="cursor last_seen_at"),
        )
        if not isinstance(self.incident_id, UUID):
            raise TypeError("cursor incident_id must be a UUID")


@dataclass(frozen=True, slots=True)
class IncidentQuery:
    service: str | None = None
    environment: str | None = None
    anomaly_type: AnomalyType | None = None
    highest_severity: AnomalySeverity | None = None
    started_after: datetime | None = None
    started_before: datetime | None = None
    last_seen_after: datetime | None = None
    last_seen_before: datetime | None = None
    minimum_finding_count: int | None = None
    limit: int = DEFAULT_INCIDENT_QUERY_LIMIT
    cursor: IncidentCursor | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "service",
            _optional_bounded(self.service, name="service", maximum=SERVICE_MAX_LENGTH),
        )
        object.__setattr__(
            self,
            "environment",
            _optional_bounded(
                self.environment, name="environment", maximum=ENVIRONMENT_MAX_LENGTH
            ),
        )
        for name in (
            "started_after",
            "started_before",
            "last_seen_after",
            "last_seen_before",
        ):
            value = getattr(self, name)
            if value is not None:
                object.__setattr__(self, name, _aware_utc(value, field_name=name))
        if (
            self.started_after is not None
            and self.started_before is not None
            and self.started_after > self.started_before
        ):
            raise ValueError("started range must not be reversed")
        if (
            self.last_seen_after is not None
            and self.last_seen_before is not None
            and self.last_seen_after > self.last_seen_before
        ):
            raise ValueError("last-seen range must not be reversed")
        if (
            isinstance(self.limit, bool)
            or not isinstance(self.limit, int)
            or not MIN_INCIDENT_QUERY_LIMIT <= self.limit <= MAX_INCIDENT_QUERY_LIMIT
        ):
            raise ValueError("limit must be between 1 and 100")
        if self.minimum_finding_count is not None and (
            isinstance(self.minimum_finding_count, bool)
            or not isinstance(self.minimum_finding_count, int)
            or not 2 <= self.minimum_finding_count <= MAXIMUM_INCIDENT_FINDING_COUNT
        ):
            raise ValueError("minimum_finding_count must be between 2 and 10000")


@dataclass(frozen=True, slots=True)
class IncidentPage:
    items: tuple[PersistedIncident, ...]
    next_cursor: IncidentCursor | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.items, tuple):
            raise TypeError("items must be a tuple")
