"""SQLAlchemy read adapter for persisted anomaly findings."""

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.application.contracts.anomaly_reader import AnomalyFindingReader
from app.application.queries.anomalies import (
    AnomalyFindingCursor,
    AnomalyFindingPage,
    AnomalyFindingQuery,
)
from app.infrastructure.database.mapper import map_anomaly_finding_record
from app.infrastructure.database.models import AnomalyFindingRecord


class SqlAlchemyAnomalyFindingReader(AnomalyFindingReader):
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def list(self, query: AnomalyFindingQuery) -> AnomalyFindingPage:
        statement = select(AnomalyFindingRecord)
        if query.event_id is not None:
            statement = statement.where(AnomalyFindingRecord.event_id == query.event_id)
        if query.anomaly_type is not None:
            statement = statement.where(
                AnomalyFindingRecord.anomaly_type == query.anomaly_type.value
            )
        if query.severity is not None:
            statement = statement.where(
                AnomalyFindingRecord.severity == query.severity.value
            )
        if query.rule_id is not None:
            statement = statement.where(AnomalyFindingRecord.rule_id == query.rule_id)
        if query.start_time is not None:
            statement = statement.where(
                AnomalyFindingRecord.created_at >= query.start_time
            )
        if query.end_time is not None:
            statement = statement.where(
                AnomalyFindingRecord.created_at <= query.end_time
            )
        if query.cursor is not None:
            statement = statement.where(
                or_(
                    AnomalyFindingRecord.created_at < query.cursor.created_at,
                    and_(
                        AnomalyFindingRecord.created_at == query.cursor.created_at,
                        AnomalyFindingRecord.id < query.cursor.finding_id,
                    ),
                )
            )
        statement = statement.order_by(
            AnomalyFindingRecord.created_at.desc(), AnomalyFindingRecord.id.desc()
        ).limit(query.limit + 1)
        async with self._session_factory() as session:
            records = list((await session.scalars(statement)).all())
        items = tuple(
            map_anomaly_finding_record(record) for record in records[: query.limit]
        )
        next_cursor = None
        if len(records) > query.limit:
            final = items[-1]
            next_cursor = AnomalyFindingCursor(final.created_at, final.id)
        return AnomalyFindingPage(items, next_cursor)
