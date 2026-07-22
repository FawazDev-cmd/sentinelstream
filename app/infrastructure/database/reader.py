"""SQLAlchemy read adapter for persisted log events."""

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.application.contracts.reader import LogEventReader
from app.application.queries.logs import LogEventCursor, LogEventPage, LogEventQuery
from app.infrastructure.database.mapper import map_log_event_record
from app.infrastructure.database.models import LogEventRecord


class SqlAlchemyLogEventReader(LogEventReader):
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def list(self, query: LogEventQuery) -> LogEventPage:
        statement = select(LogEventRecord)
        if query.service is not None:
            statement = statement.where(LogEventRecord.service == query.service)
        if query.environment is not None:
            statement = statement.where(LogEventRecord.environment == query.environment)
        if query.level is not None:
            statement = statement.where(LogEventRecord.level == query.level.value)
        if query.start_time is not None:
            statement = statement.where(LogEventRecord.timestamp >= query.start_time)
        if query.end_time is not None:
            statement = statement.where(LogEventRecord.timestamp <= query.end_time)
        if query.cursor is not None:
            statement = statement.where(
                or_(
                    LogEventRecord.timestamp < query.cursor.timestamp,
                    and_(
                        LogEventRecord.timestamp == query.cursor.timestamp,
                        LogEventRecord.event_id < query.cursor.event_id,
                    ),
                )
            )
        statement = statement.order_by(
            LogEventRecord.timestamp.desc(), LogEventRecord.event_id.desc()
        ).limit(query.limit + 1)
        async with self._session_factory() as session:
            records = list((await session.scalars(statement)).all())
        has_more = len(records) > query.limit
        events = tuple(
            map_log_event_record(record) for record in records[: query.limit]
        )
        next_cursor = None
        if has_more:
            final = events[-1]
            next_cursor = LogEventCursor(
                timestamp=final.timestamp, event_id=final.event_id
            )
        return LogEventPage(items=events, next_cursor=next_cursor)
