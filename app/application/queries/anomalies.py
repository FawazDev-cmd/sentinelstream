"""Framework-independent persisted-anomaly query values."""

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from app.domain.anomalies import AnomalySeverity, AnomalyType
from app.domain.anomalies.models import RULE_ID_MAX_LENGTH

DEFAULT_ANOMALY_QUERY_LIMIT = 50
MIN_ANOMALY_QUERY_LIMIT = 1
MAX_ANOMALY_QUERY_LIMIT = 100


def _aware_utc(value: datetime, *, field_name: str) -> datetime:
    if not isinstance(value, datetime):
        raise TypeError(f"{field_name} must be a datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
    return value.astimezone(UTC)


@dataclass(frozen=True, slots=True)
class PersistedAnomalyFinding:
    id: UUID
    event_id: UUID
    anomaly_type: AnomalyType
    severity: AnomalySeverity
    rule_id: str
    title: str
    evidence: tuple[str, ...]
    created_at: datetime

    def __post_init__(self) -> None:
        if not isinstance(self.id, UUID) or not isinstance(self.event_id, UUID):
            raise TypeError("finding and event IDs must be UUIDs")
        if not isinstance(self.anomaly_type, AnomalyType):
            raise TypeError("anomaly_type must be an AnomalyType")
        if not isinstance(self.severity, AnomalySeverity):
            raise TypeError("severity must be an AnomalySeverity")
        if not isinstance(self.evidence, tuple) or not all(
            isinstance(item, str) and bool(item.strip()) for item in self.evidence
        ):
            raise TypeError("evidence must be a tuple of nonblank strings")
        object.__setattr__(
            self, "created_at", _aware_utc(self.created_at, field_name="created_at")
        )


@dataclass(frozen=True, slots=True)
class AnomalyFindingCursor:
    created_at: datetime
    finding_id: UUID

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "created_at",
            _aware_utc(self.created_at, field_name="cursor created_at"),
        )
        if not isinstance(self.finding_id, UUID):
            raise TypeError("cursor finding_id must be a UUID")


@dataclass(frozen=True, slots=True)
class AnomalyFindingQuery:
    event_id: UUID | None = None
    anomaly_type: AnomalyType | None = None
    severity: AnomalySeverity | None = None
    rule_id: str | None = None
    start_time: datetime | None = None
    end_time: datetime | None = None
    limit: int = DEFAULT_ANOMALY_QUERY_LIMIT
    cursor: AnomalyFindingCursor | None = None

    def __post_init__(self) -> None:
        if self.event_id is not None and not isinstance(self.event_id, UUID):
            raise TypeError("event_id must be a UUID")
        if self.anomaly_type is not None and not isinstance(
            self.anomaly_type, AnomalyType
        ):
            raise TypeError("anomaly_type must be an AnomalyType")
        if self.severity is not None and not isinstance(self.severity, AnomalySeverity):
            raise TypeError("severity must be an AnomalySeverity")
        if self.rule_id is not None:
            if not isinstance(self.rule_id, str):
                raise TypeError("rule_id must be a string")
            if not self.rule_id.strip():
                raise ValueError("rule_id must not be blank")
            if len(self.rule_id) > RULE_ID_MAX_LENGTH:
                raise ValueError(
                    f"rule_id must be at most {RULE_ID_MAX_LENGTH} characters"
                )
        if isinstance(self.limit, bool) or not isinstance(self.limit, int):
            raise TypeError("limit must be an integer")
        if not MIN_ANOMALY_QUERY_LIMIT <= self.limit <= MAX_ANOMALY_QUERY_LIMIT:
            raise ValueError(
                f"limit must be between {MIN_ANOMALY_QUERY_LIMIT} and "
                f"{MAX_ANOMALY_QUERY_LIMIT}"
            )
        if self.start_time is not None:
            object.__setattr__(
                self, "start_time", _aware_utc(self.start_time, field_name="start_time")
            )
        if self.end_time is not None:
            object.__setattr__(
                self, "end_time", _aware_utc(self.end_time, field_name="end_time")
            )
        if (
            self.start_time is not None
            and self.end_time is not None
            and self.start_time > self.end_time
        ):
            raise ValueError("start_time must not be later than end_time")
        if self.cursor is not None and not isinstance(
            self.cursor, AnomalyFindingCursor
        ):
            raise TypeError("cursor must be an AnomalyFindingCursor")


@dataclass(frozen=True, slots=True)
class AnomalyFindingPage:
    items: tuple[PersistedAnomalyFinding, ...]
    next_cursor: AnomalyFindingCursor | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.items, tuple):
            raise TypeError("items must be a tuple")
