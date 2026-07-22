"""Guarded PostgreSQL coverage for Day 14 incident generation."""

import asyncio
from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from sqlalchemy import delete, func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from alembic import command
from app.application.incidents import (
    DeterministicIncidentGrouper,
    IncidentGroupingPolicy,
)
from app.application.incidents.generation import (
    GenerateIncidents,
    IncidentGenerationRequest,
)
from app.application.incidents.persistence import IncidentPersistence
from app.domain.incidents import IncidentCandidate
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
from tests.integration.test_postgresql import REVISION, alembic_config, database_url

pytestmark = pytest.mark.integration
BASE = datetime(2026, 7, 23, 12, tzinfo=UTC)
EVENT_IDS = tuple(UUID(int=14_000 + index) for index in range(8))
FINDING_IDS = tuple(UUID(int=14_100 + index) for index in range(8))


def event(
    index: int, minute: int, *, service: str = "day14-payments"
) -> LogEventRecord:
    return LogEventRecord(
        event_id=EVENT_IDS[index],
        timestamp=BASE + timedelta(minutes=minute),
        received_at=BASE,
        service=service,
        environment="day14-test",
        level="ERROR",
        message="private day14 source",
        exception_type=None,
        exception_message=None,
        latency_ms=None,
        status_code=None,
        trace_id=None,
        request_id=None,
        host=None,
        event_metadata={"private": "day14"},
    )


def finding(index: int, created_second: int) -> AnomalyFindingRecord:
    return AnomalyFindingRecord(
        id=FINDING_IDS[index],
        event_id=EVENT_IDS[index],
        anomaly_type="high_latency",
        severity="high",
        rule_id=f"day14.{index}.v1",
        title="Day 14 finding",
        evidence=[f"index={index}"],
        created_at=BASE + timedelta(seconds=created_second),
    )


async def cleanup(factory: async_sessionmaker) -> None:  # type: ignore[type-arg]
    async with factory() as session:
        incident_ids = select(IncidentFindingRecord.incident_id).where(
            IncidentFindingRecord.finding_id.in_(FINDING_IDS)
        )
        await session.execute(
            delete(IncidentRecord).where(IncidentRecord.id.in_(incident_ids))
        )
        await session.execute(
            delete(LogEventRecord).where(LogEventRecord.event_id.in_(EVENT_IDS))
        )
        await session.commit()


async def seed(factory: async_sessionmaker) -> None:  # type: ignore[type-arg]
    await cleanup(factory)
    moments = (0, 4, 8, 20, 24, 30, 30, 30)
    services = ("day14-payments",) * 5 + ("day14-ordering",) * 3
    created = (0, 1, 90_000, 3, 4, 10, 11, 11)
    async with factory() as session:
        session.add_all(
            [
                event(index, moments[index], service=services[index])
                for index in range(8)
            ]
        )
        await session.flush()
        session.add_all([finding(index, created[index]) for index in range(8)])
        await session.commit()


def test_eligible_reader_revision_boundaries_order_exclusion_and_cleanup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    url = database_url()
    monkeypatch.setenv("SENTINELSTREAM_DATABASE_URL", url)
    command.upgrade(alembic_config(), "head")
    engine = create_async_engine(url, pool_pre_ping=True)
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async def scenario() -> None:
        await seed(factory)
        async with factory() as session:
            assert (
                await session.scalar(text("SELECT version_num FROM alembic_version"))
                == REVISION
            )
            assigned_incident = IncidentRecord(
                id=UUID(int=14_900),
                service="assigned-day14",
                environment="day14-test",
                anomaly_type="high_latency",
                started_at=BASE,
                last_seen_at=BASE,
                finding_count=2,
                highest_severity="high",
                created_at=BASE,
            )
            session.add(assigned_incident)
            await session.flush()
            session.add_all(
                [
                    IncidentFindingRecord(
                        incident_id=assigned_incident.id,
                        finding_id=FINDING_IDS[index],
                        position=position,
                        created_at=BASE,
                    )
                    for position, index in enumerate((0, 3))
                ]
            )
            await session.commit()

        reader = SqlAlchemyEligibleIncidentFindingReader(factory)
        lower = BASE + timedelta(minutes=4)
        upper = BASE + timedelta(minutes=30)
        pages = []
        cursor = None
        while True:
            page = await reader.read_batch(
                event_time_from=lower, event_time_to=upper, limit=2, after=cursor
            )
            pages.append(page)
            if page.next_cursor is None:
                break
            cursor = page.next_cursor
        items = [item for page in pages for item in page.items]
        ids = [item.finding.id for item in items]
        assert ids == [
            FINDING_IDS[1],
            FINDING_IDS[2],
            FINDING_IDS[4],
            FINDING_IDS[5],
            FINDING_IDS[6],
            FINDING_IDS[7],
        ]
        assert len(ids) == len(set(ids)) == 6 and pages[-1].next_cursor is None
        assert FINDING_IDS[0] not in ids and FINDING_IDS[3] not in ids
        assert items[0].event_timestamp == BASE + timedelta(minutes=4)
        assert items[1].finding.created_at > upper
        assert (
            items[-3].event_timestamp
            == items[-2].event_timestamp
            == items[-1].event_timestamp
        )
        assert [item.finding.id for item in items[-2:]] == sorted(FINDING_IDS[6:8])
        assert (
            items[0].service == "day14-payments"
            and items[0].environment == "day14-test"
        )
        assert not hasattr(items[0], "message") and not hasattr(items[0], "metadata")
        await cleanup(factory)
        async with factory() as session:
            assert (
                await session.scalar(
                    select(func.count())
                    .select_from(LogEventRecord)
                    .where(LogEventRecord.event_id.in_(EVENT_IDS))
                )
                == 0
            )

    try:
        asyncio.run(scenario())
    finally:
        asyncio.run(cleanup(factory))
        asyncio.run(engine.dispose())


class FailSecondPersistence(IncidentPersistence):
    def __init__(self, delegate: IncidentPersistence) -> None:
        self.delegate = delegate
        self.calls = 0

    async def persist(self, candidate: IncidentCandidate) -> UUID:
        self.calls += 1
        if self.calls == 2:
            raise RuntimeError("forced Day 14 integration failure")
        return await self.delegate.persist(candidate)


def test_generation_batch_invariance_repeat_and_partial_retry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    url = database_url()
    monkeypatch.setenv("SENTINELSTREAM_DATABASE_URL", url)
    command.upgrade(alembic_config(), "head")
    engine = create_async_engine(url, pool_pre_ping=True)
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async def run(batch_size: int, persistence: IncidentPersistence | None = None):  # type: ignore[no-untyped-def]
        policy = IncidentGroupingPolicy()
        return await GenerateIncidents(
            SqlAlchemyEligibleIncidentFindingReader(factory),
            DeterministicIncidentGrouper(policy),
            persistence or SqlAlchemyIncidentPersistence(factory),
            policy,
        ).execute(
            IncidentGenerationRequest(BASE, BASE + timedelta(minutes=24), batch_size)
        )

    async def scenario() -> None:
        await seed(factory)
        first = await run(2)
        assert first.findings_read == 5 and first.incidents_persisted == 2
        async with factory() as session:
            rows = list(
                (
                    await session.scalars(
                        select(IncidentFindingRecord)
                        .where(IncidentFindingRecord.finding_id.in_(FINDING_IDS[:5]))
                        .order_by(
                            IncidentFindingRecord.incident_id,
                            IncidentFindingRecord.position,
                        )
                    )
                ).all()
            )
            assert sorted(row.position for row in rows) == [0, 0, 1, 1, 2]
        repeated = await run(3)
        assert repeated.findings_read == repeated.incidents_persisted == 0
        assert repeated.incident_ids == ()
        first_ids = first.incident_ids

        await cleanup(factory)
        await seed(factory)
        equivalent = await run(500)
        assert equivalent.incident_ids == first_ids
        async with factory() as session:
            assert (
                await session.scalar(
                    select(func.count())
                    .select_from(IncidentRecord)
                    .where(IncidentRecord.id.in_(first_ids))
                )
                == 2
            )
            assert (
                await session.scalar(
                    select(func.count())
                    .select_from(IncidentFindingRecord)
                    .where(IncidentFindingRecord.finding_id.in_(FINDING_IDS[:5]))
                )
                == 5
            )

        await cleanup(factory)
        await seed(factory)
        failing = FailSecondPersistence(SqlAlchemyIncidentPersistence(factory))
        with pytest.raises(RuntimeError):
            await run(2, failing)
        retry = await run(3)
        assert retry.findings_read == 2 and retry.incidents_persisted == 1
        final = await run(2)
        assert final.findings_read == final.incidents_persisted == 0
        async with factory() as session:
            with pytest.raises(IntegrityError):
                async with session.begin():
                    session.add(
                        IncidentFindingRecord(
                            incident_id=first_ids[0],
                            finding_id=FINDING_IDS[0],
                            position=99,
                            created_at=BASE,
                        )
                    )
                    await session.flush()
        await cleanup(factory)

    try:
        asyncio.run(scenario())
    finally:
        asyncio.run(cleanup(factory))
        asyncio.run(engine.dispose())
