"""SQLAlchemy repository for normalized log events."""

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.application.contracts.repository import LogEventRepository
from app.domain.logs import LogEvent
from app.infrastructure.database.mapper import map_log_event


class SqlAlchemyLogEventRepository(LogEventRepository):
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def add(self, event: LogEvent) -> None:
        async with self._session_factory() as session:
            try:
                session.add(map_log_event(event))
                await session.commit()
            except Exception:
                await session.rollback()
                raise
