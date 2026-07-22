"""One-session, one-transaction persistence for events and findings."""

from collections.abc import Sequence

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.application.contracts.clock import Clock, SystemClock
from app.application.contracts.detection_persistence import DetectionPersistence
from app.domain.anomalies import AnomalyFinding
from app.domain.logs import LogEvent
from app.infrastructure.database.mapper import map_anomaly_finding, map_log_event


class SqlAlchemyDetectionPersistence(DetectionPersistence):
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        clock: Clock | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._clock = clock or SystemClock()

    async def persist(
        self, event: LogEvent, findings: Sequence[AnomalyFinding]
    ) -> None:
        async with self._session_factory() as session, session.begin():
            session.add(map_log_event(event))
            await session.flush()
            created_at = self._clock.now()
            records = [
                map_anomaly_finding(event.event_id, finding, created_at)
                for finding in findings
            ]
            session.add_all(records)
