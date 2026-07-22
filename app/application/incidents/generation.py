"""Framework-independent incident generation orchestration."""

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol
from uuid import UUID

from app.application.incidents.contracts import IncidentGrouper
from app.application.incidents.models import (
    IncidentGroupingInput,
    IncidentGroupingPolicy,
)
from app.application.incidents.persistence import IncidentPersistence
from app.application.queries.anomalies import PersistedAnomalyFinding
from app.domain.logs.models import ENVIRONMENT_MAX_LENGTH, SERVICE_MAX_LENGTH

DEFAULT_GENERATION_BATCH_SIZE = 500
MIN_GENERATION_BATCH_SIZE = 2
MAX_GENERATION_BATCH_SIZE = 10_000


def _utc(value: datetime, name: str) -> datetime:
    if not isinstance(value, datetime):
        raise TypeError(f"{name} must be a datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")
    return value.astimezone(UTC)


def _bounded(value: str, name: str, maximum: int) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{name} must be a string")
    if not value.strip():
        raise ValueError(f"{name} must not be blank")
    if len(value) > maximum:
        raise ValueError(f"{name} must be at most {maximum} characters")
    return value


@dataclass(frozen=True, slots=True)
class IncidentGenerationRequest:
    event_time_from: datetime
    event_time_to: datetime
    batch_size: int = DEFAULT_GENERATION_BATCH_SIZE

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "event_time_from", _utc(self.event_time_from, "event_time_from")
        )
        object.__setattr__(
            self, "event_time_to", _utc(self.event_time_to, "event_time_to")
        )
        if self.event_time_from > self.event_time_to:
            raise ValueError("event_time_from must not be later than event_time_to")
        if isinstance(self.batch_size, bool) or not isinstance(self.batch_size, int):
            raise TypeError("batch_size must be an integer")
        if (
            not MIN_GENERATION_BATCH_SIZE
            <= self.batch_size
            <= MAX_GENERATION_BATCH_SIZE
        ):
            raise ValueError("batch_size must be between 2 and 10000")


@dataclass(frozen=True, slots=True)
class EligibleIncidentFinding:
    finding: PersistedAnomalyFinding
    service: str
    environment: str
    event_timestamp: datetime

    def __post_init__(self) -> None:
        if not isinstance(self.finding, PersistedAnomalyFinding):
            raise TypeError("finding must be a PersistedAnomalyFinding")
        object.__setattr__(
            self, "service", _bounded(self.service, "service", SERVICE_MAX_LENGTH)
        )
        object.__setattr__(
            self,
            "environment",
            _bounded(self.environment, "environment", ENVIRONMENT_MAX_LENGTH),
        )
        object.__setattr__(
            self, "event_timestamp", _utc(self.event_timestamp, "event_timestamp")
        )

    def to_grouping_input(self) -> IncidentGroupingInput:
        return IncidentGroupingInput(
            self.finding, self.service, self.environment, self.event_timestamp
        )


@dataclass(frozen=True, slots=True, order=True)
class EligibleIncidentFindingCursor:
    event_timestamp: datetime
    finding_created_at: datetime
    finding_id: UUID

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "event_timestamp",
            _utc(self.event_timestamp, "cursor event_timestamp"),
        )
        object.__setattr__(
            self,
            "finding_created_at",
            _utc(self.finding_created_at, "cursor finding_created_at"),
        )
        if not isinstance(self.finding_id, UUID):
            raise TypeError("cursor finding_id must be a UUID")


@dataclass(frozen=True, slots=True)
class EligibleIncidentFindingPage:
    items: tuple[EligibleIncidentFinding, ...]
    next_cursor: EligibleIncidentFindingCursor | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.items, tuple):
            raise TypeError("items must be a tuple")
        if not all(isinstance(item, EligibleIncidentFinding) for item in self.items):
            raise TypeError("items must contain eligible incident findings")


class EligibleIncidentFindingReader(Protocol):
    async def read_batch(
        self,
        *,
        event_time_from: datetime,
        event_time_to: datetime,
        limit: int,
        after: EligibleIncidentFindingCursor | None = None,
    ) -> EligibleIncidentFindingPage: ...


@dataclass(frozen=True, slots=True)
class IncidentGenerationResult:
    findings_read: int
    candidates_generated: int
    incidents_persisted: int
    incident_ids: tuple[UUID, ...]
    batches_read: int = 0

    def __post_init__(self) -> None:
        counts = (
            self.findings_read,
            self.candidates_generated,
            self.incidents_persisted,
            self.batches_read,
        )
        if any(
            isinstance(value, bool) or not isinstance(value, int) or value < 0
            for value in counts
        ):
            raise ValueError("generation counts must be nonnegative integers")
        if not isinstance(self.incident_ids, tuple) or not all(
            isinstance(value, UUID) for value in self.incident_ids
        ):
            raise TypeError("incident_ids must be a tuple of UUIDs")
        if self.incidents_persisted != len(self.incident_ids):
            raise ValueError("persisted count must match incident IDs")
        if self.candidates_generated != self.incidents_persisted:
            raise ValueError(
                "fail-fast generation requires equal candidate and persisted counts"
            )


class DuplicateEligibleIncidentFindingError(ValueError):
    def __init__(self, finding_id: UUID) -> None:
        super().__init__(f"duplicate eligible finding_id={finding_id}")


class IncidentGenerationCursorProgressError(ValueError):
    def __init__(self) -> None:
        super().__init__("eligible finding cursor did not advance")


class GenerateIncidents:
    def __init__(
        self,
        reader: EligibleIncidentFindingReader,
        grouper: IncidentGrouper,
        persistence: IncidentPersistence,
        policy: IncidentGroupingPolicy,
    ) -> None:
        self._reader = reader
        self._grouper = grouper
        self._persistence = persistence
        self._policy = policy

    async def execute(
        self, request: IncidentGenerationRequest
    ) -> IncidentGenerationResult:
        if not isinstance(request, IncidentGenerationRequest):
            raise TypeError("request must be an IncidentGenerationRequest")
        values: list[EligibleIncidentFinding] = []
        seen: set[UUID] = set()
        after: EligibleIncidentFindingCursor | None = None
        batches = 0
        while True:
            page = await self._reader.read_batch(
                event_time_from=request.event_time_from,
                event_time_to=request.event_time_to,
                limit=request.batch_size,
                after=after,
            )
            batches += 1
            for value in page.items:
                if value.finding.id in seen:
                    raise DuplicateEligibleIncidentFindingError(value.finding.id)
                seen.add(value.finding.id)
                values.append(value)
            if page.next_cursor is None:
                break
            if after is not None and page.next_cursor <= after:
                raise IncidentGenerationCursorProgressError()
            after = page.next_cursor
        candidates = self._grouper.group(
            tuple(value.to_grouping_input() for value in values)
        )
        ids = []
        for candidate in candidates:
            ids.append(await self._persistence.persist(candidate))
        return IncidentGenerationResult(
            len(values), len(candidates), len(ids), tuple(ids), batches
        )
