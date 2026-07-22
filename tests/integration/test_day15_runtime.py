"""Guarded PostgreSQL smoke test for automatic runtime incident generation."""

import asyncio
from datetime import UTC, datetime
from uuid import UUID

import pytest
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from alembic import command
from app.application.anomalies import (
    RuleBasedAnomalyDetector,
    build_default_anomaly_rules,
)
from app.application.anomalies.policy import DetectionPolicy
from app.application.incidents import (
    DeterministicIncidentGrouper,
    GenerateIncidents,
    IncidentGroupingPolicy,
)
from app.application.services.persistence import DetectAndPersistLogEventProcessor
from app.domain.logs import LogEvent, LogLevel
from app.infrastructure.database.detection_persistence import (
    SqlAlchemyDetectionPersistence,
)
from app.infrastructure.database.eligible_incident_reader import (
    SqlAlchemyEligibleIncidentFindingReader,
)
from app.infrastructure.database.incident_persistence import (
    SqlAlchemyIncidentPersistence,
)
from app.infrastructure.database.models import (
    AnomalyFindingRecord,
    IncidentFindingRecord,
    IncidentRecord,
    LogEventRecord,
)
from tests.integration.test_postgresql import alembic_config, database_url

pytestmark = pytest.mark.integration
EVENT_IDS = tuple(UUID(int=15_000 + index) for index in range(3))
MOMENT = datetime(2026, 7, 23, 14, tzinfo=UTC)


def test_runtime_processor_automatically_generates_incidents(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    url = database_url()
    monkeypatch.setenv("SENTINELSTREAM_DATABASE_URL", url)
    command.upgrade(alembic_config(), "head")
    engine = create_async_engine(url, pool_pre_ping=True)
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async def cleanup() -> None:
        async with factory() as session:
            finding_ids = select(AnomalyFindingRecord.id).where(
                AnomalyFindingRecord.event_id.in_(EVENT_IDS)
            )
            incident_ids = select(IncidentFindingRecord.incident_id).where(
                IncidentFindingRecord.finding_id.in_(finding_ids)
            )
            await session.execute(
                delete(IncidentRecord).where(IncidentRecord.id.in_(incident_ids))
            )
            await session.execute(
                delete(LogEventRecord).where(LogEventRecord.event_id.in_(EVENT_IDS))
            )
            await session.commit()

    async def scenario() -> None:
        await cleanup()
        policy = IncidentGroupingPolicy()
        generator = GenerateIncidents(
            SqlAlchemyEligibleIncidentFindingReader(factory),
            DeterministicIncidentGrouper(policy),
            SqlAlchemyIncidentPersistence(factory),
            policy,
        )
        processor = DetectAndPersistLogEventProcessor(
            RuleBasedAnomalyDetector(build_default_anomaly_rules(DetectionPolicy())),
            SqlAlchemyDetectionPersistence(factory),
            generator,
        )

        def event(index: int) -> LogEvent:
            return LogEvent(
                event_id=EVENT_IDS[index],
                timestamp=MOMENT,
                received_at=MOMENT,
                service="day15-runtime",
                environment="day15-test",
                level=LogLevel.ERROR,
                message="private",
                latency_ms=6000,
            )

        await processor.process(event(0))
        await processor.process(event(1))
        async with factory() as session:
            incidents = await session.scalar(
                select(func.count())
                .select_from(IncidentRecord)
                .where(IncidentRecord.service == "day15-runtime")
            )
            assignments = await session.scalar(
                select(func.count())
                .select_from(IncidentFindingRecord)
                .join(
                    AnomalyFindingRecord,
                    IncidentFindingRecord.finding_id == AnomalyFindingRecord.id,
                )
                .where(AnomalyFindingRecord.event_id.in_(EVENT_IDS))
            )
        assert incidents == 2 and assignments == 4

        await processor.process(event(2))
        async with factory() as session:
            assert (
                await session.scalar(
                    select(func.count())
                    .select_from(IncidentRecord)
                    .where(IncidentRecord.service == "day15-runtime")
                )
                == incidents
            )
            rows = list(
                (
                    await session.scalars(
                        select(IncidentFindingRecord)
                        .join(
                            AnomalyFindingRecord,
                            IncidentFindingRecord.finding_id == AnomalyFindingRecord.id,
                        )
                        .where(AnomalyFindingRecord.event_id.in_(EVENT_IDS))
                        .order_by(
                            IncidentFindingRecord.incident_id,
                            IncidentFindingRecord.position,
                        )
                    )
                ).all()
            )
            assert len(rows) == len({row.finding_id for row in rows}) == assignments

    try:
        asyncio.run(scenario())
    finally:
        asyncio.run(cleanup())
        asyncio.run(engine.dispose())
