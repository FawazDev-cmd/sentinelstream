"""SQLAlchemy reader for unassigned anomaly findings eligible for incidents."""

from datetime import datetime

from sqlalchemy import and_, exists, or_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.application.incidents.generation import (
    EligibleIncidentFinding,
    EligibleIncidentFindingCursor,
    EligibleIncidentFindingPage,
    EligibleIncidentFindingReader,
)
from app.application.queries.anomalies import PersistedAnomalyFinding
from app.domain.anomalies import AnomalySeverity, AnomalyType
from app.infrastructure.database.models import (
    AnomalyFindingRecord,
    IncidentFindingRecord,
    LogEventRecord,
)


class EligibleIncidentFindingMappingError(ValueError):
    """Raised when joined persisted state is invalid."""


def map_eligible_incident_finding(
    finding: AnomalyFindingRecord, event: LogEventRecord
) -> EligibleIncidentFinding:
    try:
        if finding.event_id != event.event_id:
            raise ValueError("event identity mismatch")
        persisted = PersistedAnomalyFinding(
            finding.id,
            finding.event_id,
            AnomalyType(finding.anomaly_type),
            AnomalySeverity(finding.severity),
            finding.rule_id,
            finding.title,
            tuple(finding.evidence),
            finding.created_at,
        )
        return EligibleIncidentFinding(
            persisted, event.service, event.environment, event.timestamp
        )
    except (TypeError, ValueError) as error:
        raise EligibleIncidentFindingMappingError(
            "Eligible incident finding state is invalid."
        ) from error


class SqlAlchemyEligibleIncidentFindingReader(EligibleIncidentFindingReader):
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def read_batch(
        self,
        *,
        event_time_from: datetime,
        event_time_to: datetime,
        limit: int,
        after: EligibleIncidentFindingCursor | None = None,
    ) -> EligibleIncidentFindingPage:
        assigned = exists(
            select(1).where(IncidentFindingRecord.finding_id == AnomalyFindingRecord.id)
        )
        statement = (
            select(AnomalyFindingRecord, LogEventRecord)
            .join(
                LogEventRecord, AnomalyFindingRecord.event_id == LogEventRecord.event_id
            )
            .where(
                ~assigned,
                LogEventRecord.timestamp >= event_time_from,
                LogEventRecord.timestamp <= event_time_to,
            )
        )
        if after is not None:
            statement = statement.where(
                or_(
                    LogEventRecord.timestamp > after.event_timestamp,
                    and_(
                        LogEventRecord.timestamp == after.event_timestamp,
                        AnomalyFindingRecord.created_at > after.finding_created_at,
                    ),
                    and_(
                        LogEventRecord.timestamp == after.event_timestamp,
                        AnomalyFindingRecord.created_at == after.finding_created_at,
                        AnomalyFindingRecord.id > after.finding_id,
                    ),
                )
            )
        statement = statement.order_by(
            LogEventRecord.timestamp.asc(),
            AnomalyFindingRecord.created_at.asc(),
            AnomalyFindingRecord.id.asc(),
        ).limit(limit + 1)
        async with self._session_factory() as session:
            rows = list((await session.execute(statement)).all())
        items = tuple(
            map_eligible_incident_finding(finding, event)
            for finding, event in rows[:limit]
        )
        cursor = None
        if len(rows) > limit:
            final = items[-1]
            cursor = EligibleIncidentFindingCursor(
                final.event_timestamp, final.finding.created_at, final.finding.id
            )
        return EligibleIncidentFindingPage(items, cursor)
