"""Transactional, idempotent persistence for incident candidates."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.application.contracts.clock import Clock, SystemClock
from app.application.incidents.exceptions import (
    IncidentFindingAlreadyAssignedError,
    IncidentPersistenceConflictError,
)
from app.application.incidents.identity import build_incident_id
from app.application.incidents.persistence import IncidentPersistence
from app.domain.incidents import IncidentCandidate
from app.infrastructure.database.incident_mapper import map_incident_candidate
from app.infrastructure.database.models import IncidentFindingRecord, IncidentRecord


class SqlAlchemyIncidentPersistence(IncidentPersistence):
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        clock: Clock | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._clock = clock or SystemClock()

    async def persist(self, candidate: IncidentCandidate) -> UUID:
        incident_id = build_incident_id(candidate)
        try:
            async with self._session_factory() as session, session.begin():
                existing = await session.get(IncidentRecord, incident_id)
                if existing is not None:
                    memberships = tuple(
                        (
                            await session.scalars(
                                select(IncidentFindingRecord)
                                .where(IncidentFindingRecord.incident_id == incident_id)
                                .order_by(IncidentFindingRecord.position)
                            )
                        ).all()
                    )
                    self._verify_existing(candidate, existing, memberships)
                    return incident_id
                incident, memberships = map_incident_candidate(
                    candidate, incident_id, self._clock.now()
                )
                session.add(incident)
                await session.flush()
                session.add_all(list(memberships))
        except IntegrityError as error:
            raise IncidentFindingAlreadyAssignedError(
                "an incident finding is already assigned"
            ) from error
        return incident_id

    @staticmethod
    def _verify_existing(
        candidate: IncidentCandidate,
        incident: IncidentRecord,
        memberships: tuple[IncidentFindingRecord, ...],
    ) -> None:
        immutable = (
            incident.service,
            incident.environment,
            incident.anomaly_type,
            incident.started_at,
            incident.last_seen_at,
            incident.finding_count,
            incident.highest_severity,
        )
        expected = (
            candidate.key.service,
            candidate.key.environment,
            candidate.key.anomaly_type.value,
            candidate.started_at,
            candidate.last_seen_at,
            candidate.finding_count,
            candidate.highest_severity.value,
        )
        membership_state = tuple(
            (membership.finding_id, membership.position) for membership in memberships
        )
        expected_memberships = tuple(
            (finding_id, position)
            for position, finding_id in enumerate(candidate.finding_ids)
        )
        if immutable != expected or membership_state != expected_memberships:
            raise IncidentPersistenceConflictError(
                f"persisted incident conflicts with incident_id={incident.id}"
            )
