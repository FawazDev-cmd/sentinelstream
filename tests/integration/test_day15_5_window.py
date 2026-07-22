"""Guarded PostgreSQL coverage for the corrected runtime lookback window."""

import asyncio
from datetime import UTC, datetime, timedelta
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
BASE = datetime(2026, 7, 24, 12, tzinfo=UTC)
EVENT_IDS = tuple(UUID(int=15_500 + index) for index in range(7))


def test_runtime_lookback_groups_nearby_distinct_event_times(
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

    def event(
        index: int,
        minute: int,
        *,
        service: str = "day155-runtime",
        environment: str = "day155-test",
    ) -> LogEvent:
        timestamp = BASE + timedelta(minutes=minute)
        return LogEvent(
            event_id=EVENT_IDS[index],
            timestamp=timestamp,
            received_at=timestamp,
            service=service,
            environment=environment,
            level=LogLevel.ERROR,
            message="private",
            latency_ms=6000,
        )

    async def scenario() -> None:
        await cleanup()
        detector = RuleBasedAnomalyDetector(
            build_default_anomaly_rules(DetectionPolicy())
        )
        persistence = SqlAlchemyDetectionPersistence(factory)
        initial = (
            event(0, 0),
            event(1, 4),
            event(3, -120),
            event(4, 6, service="day155-other"),
            event(5, 7, environment="day155-other"),
        )
        for value in initial:
            await persistence.persist(value, detector.detect(value).findings)

        policy = IncidentGroupingPolicy()
        generator = GenerateIncidents(
            SqlAlchemyEligibleIncidentFindingReader(factory),
            DeterministicIncidentGrouper(policy),
            SqlAlchemyIncidentPersistence(factory),
            policy,
        )
        processor = DetectAndPersistLogEventProcessor(
            detector, persistence, generator, timedelta(hours=1)
        )
        await processor.process(event(2, 8))

        async with factory() as session:
            incidents = list(
                (
                    await session.scalars(
                        select(IncidentRecord)
                        .where(IncidentRecord.service == "day155-runtime")
                        .order_by(IncidentRecord.anomaly_type)
                    )
                ).all()
            )
            memberships = list(
                (
                    await session.execute(
                        select(IncidentFindingRecord, AnomalyFindingRecord)
                        .join(
                            AnomalyFindingRecord,
                            IncidentFindingRecord.finding_id == AnomalyFindingRecord.id,
                        )
                        .where(
                            IncidentFindingRecord.incident_id.in_(
                                [item.id for item in incidents]
                            )
                        )
                        .order_by(
                            IncidentFindingRecord.incident_id,
                            IncidentFindingRecord.position,
                        )
                    )
                ).all()
            )
        assert len(incidents) == 2
        assert all(item.finding_count == 3 for item in incidents)
        assert len(memberships) == 6
        for incident in incidents:
            event_order = [
                finding.event_id
                for membership, finding in memberships
                if membership.incident_id == incident.id
            ]
            assert event_order == [EVENT_IDS[0], EVENT_IDS[1], EVENT_IDS[2]]
        assigned_event_ids = {finding.event_id for _, finding in memberships}
        assert EVENT_IDS[3] not in assigned_event_ids
        assert EVENT_IDS[4] not in assigned_event_ids
        assert EVENT_IDS[5] not in assigned_event_ids

        await processor.process(event(6, 9))
        async with factory() as session:
            assert (
                await session.scalar(
                    select(func.count())
                    .select_from(IncidentRecord)
                    .where(IncidentRecord.service == "day155-runtime")
                )
                == 2
            )
            assert (
                await session.scalar(
                    select(func.count())
                    .select_from(IncidentFindingRecord)
                    .where(
                        IncidentFindingRecord.incident_id.in_(
                            [item.id for item in incidents]
                        )
                    )
                )
                == 6
            )

    try:
        asyncio.run(scenario())
    finally:
        asyncio.run(cleanup())
        asyncio.run(engine.dispose())
