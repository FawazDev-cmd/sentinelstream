"""SQLAlchemy read adapter for persisted incidents."""

from uuid import UUID

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.application.contracts.incident_reader import IncidentReader
from app.application.queries.incidents import (
    IncidentCursor,
    IncidentPage,
    IncidentQuery,
    PersistedIncidentDetail,
)
from app.infrastructure.database.incident_read_mapper import (
    map_incident_detail,
    map_incident_record,
)
from app.infrastructure.database.models import (
    AnomalyFindingRecord,
    IncidentFindingRecord,
    IncidentRecord,
)


class SqlAlchemyIncidentReader(IncidentReader):
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def list(self, query: IncidentQuery) -> IncidentPage:
        statement = select(IncidentRecord)
        filters = (
            (query.service, IncidentRecord.service),
            (query.environment, IncidentRecord.environment),
            (
                query.anomaly_type.value if query.anomaly_type else None,
                IncidentRecord.anomaly_type,
            ),
            (
                query.highest_severity.value if query.highest_severity else None,
                IncidentRecord.highest_severity,
            ),
        )
        for value, column in filters:
            if value is not None:
                statement = statement.where(column == value)
        if query.started_after is not None:
            statement = statement.where(
                IncidentRecord.started_at >= query.started_after
            )
        if query.started_before is not None:
            statement = statement.where(
                IncidentRecord.started_at <= query.started_before
            )
        if query.last_seen_after is not None:
            statement = statement.where(
                IncidentRecord.last_seen_at >= query.last_seen_after
            )
        if query.last_seen_before is not None:
            statement = statement.where(
                IncidentRecord.last_seen_at <= query.last_seen_before
            )
        if query.minimum_finding_count is not None:
            statement = statement.where(
                IncidentRecord.finding_count >= query.minimum_finding_count
            )
        if query.cursor is not None:
            statement = statement.where(
                or_(
                    IncidentRecord.last_seen_at < query.cursor.last_seen_at,
                    and_(
                        IncidentRecord.last_seen_at == query.cursor.last_seen_at,
                        IncidentRecord.id < query.cursor.incident_id,
                    ),
                )
            )
        statement = statement.order_by(
            IncidentRecord.last_seen_at.desc(), IncidentRecord.id.desc()
        ).limit(query.limit + 1)
        async with self._session_factory() as session:
            records = list((await session.scalars(statement)).all())
        items = tuple(map_incident_record(record) for record in records[: query.limit])
        next_cursor = (
            IncidentCursor(items[-1].last_seen_at, items[-1].id)
            if len(records) > query.limit
            else None
        )
        return IncidentPage(items, next_cursor)

    async def get(self, incident_id: UUID) -> PersistedIncidentDetail | None:
        async with self._session_factory() as session:
            incident = await session.scalar(
                select(IncidentRecord).where(IncidentRecord.id == incident_id)
            )
            if incident is None:
                return None
            statement = (
                select(IncidentFindingRecord, AnomalyFindingRecord)
                .join(
                    AnomalyFindingRecord,
                    IncidentFindingRecord.finding_id == AnomalyFindingRecord.id,
                )
                .where(IncidentFindingRecord.incident_id == incident_id)
                .order_by(IncidentFindingRecord.position.asc())
            )
            rows = [
                (membership, finding)
                for membership, finding in (await session.execute(statement)).all()
            ]
        return map_incident_detail(incident, rows)
