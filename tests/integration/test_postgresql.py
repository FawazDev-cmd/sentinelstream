"""Guarded PostgreSQL migration integration test."""

import asyncio
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import cast
from uuid import UUID

import pytest
from alembic.config import Config
from sqlalchemy import Table, delete, func, inspect, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.engine.reflection import Inspector
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from alembic import command
from app.domain.logs import LogEvent, LogLevel
from app.infrastructure.database.models import LogEventRecord
from app.infrastructure.database.repository import SqlAlchemyLogEventRepository

pytestmark = pytest.mark.integration
ROOT = Path(__file__).parents[2]
REVISION = "20260722_0003"
EVENT_ID = UUID("00000000-0000-4000-8000-000000006001")
GUARD_TABLE = "sentinelstream_migration_guard"


def database_url() -> str:
    value = os.getenv("SENTINELSTREAM_TEST_DATABASE_URL")
    if not value:
        pytest.skip("SENTINELSTREAM_TEST_DATABASE_URL is not configured")
    database = make_url(value).database or ""
    if "test" not in database.casefold():
        pytest.fail("migration database name must contain 'test'")
    return value


def alembic_config() -> Config:
    return Config(str(ROOT / "alembic.ini"))


def test_upgrade_repository_downgrade_safety_and_reupgrade(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    url = database_url()
    monkeypatch.setenv("SENTINELSTREAM_DATABASE_URL", url)
    engine = create_async_engine(url, pool_pre_ping=True)
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async def prepare_guard() -> None:
        async with engine.begin() as connection:
            await connection.execute(
                text(
                    f"CREATE TABLE IF NOT EXISTS {GUARD_TABLE} (id integer PRIMARY KEY)"
                )
            )

    async def inspect_schema() -> tuple[set[str], set[str], str | None, bool]:
        async with engine.connect() as connection:

            def inspect_sync(
                sync_connection: object,
            ) -> tuple[set[str], set[str], bool]:
                inspector = cast(Inspector, inspect(sync_connection))
                columns = {item["name"] for item in inspector.get_columns("log_events")}
                indexes = {
                    cast(str, item["name"])
                    for item in inspector.get_indexes("log_events")
                }
                return columns, indexes, inspector.has_table(GUARD_TABLE)

            columns, indexes, guard = await connection.run_sync(inspect_sync)
            version = await connection.scalar(
                text("SELECT version_num FROM alembic_version")
            )
            return columns, indexes, version, guard

    async def cleanup() -> None:
        async with factory() as session:
            await session.execute(
                delete(LogEventRecord).where(LogEventRecord.event_id == EVENT_ID)
            )
            await session.commit()
        async with engine.begin() as connection:
            await connection.execute(text(f"DROP TABLE IF EXISTS {GUARD_TABLE}"))

    try:
        asyncio.run(prepare_guard())
        command.upgrade(alembic_config(), "head")
        columns, indexes, version, guard = asyncio.run(inspect_schema())
        assert version == REVISION and guard
        assert set(LogEventRecord.__table__.c.keys()) == columns
        assert {
            index.name for index in cast(Table, LogEventRecord.__table__).indexes
        } == indexes
        event = LogEvent(
            event_id=EVENT_ID,
            timestamp=datetime(2026, 7, 22, 10, tzinfo=UTC),
            received_at=datetime(2026, 7, 22, 10, 0, 1, tzinfo=UTC),
            service="migration-api",
            environment="test",
            level=LogLevel.ERROR,
            message="failure",
            metadata={"source": "migration", "items": [1, True]},  # type: ignore[dict-item]
        )
        asyncio.run(SqlAlchemyLogEventRepository(factory).add(event))
        command.upgrade(alembic_config(), "head")
        command.downgrade(alembic_config(), "base")

        async def verify_downgrade() -> tuple[bool, bool]:
            async with engine.connect() as connection:
                return await connection.run_sync(
                    lambda sync: (
                        inspect(sync).has_table("log_events"),
                        inspect(sync).has_table(GUARD_TABLE),
                    )
                )

        log_exists, guard_exists = asyncio.run(verify_downgrade())
        assert not log_exists and guard_exists
        command.upgrade(alembic_config(), "head")
        assert asyncio.run(inspect_schema())[2] == REVISION
        asyncio.run(cleanup())
    finally:
        asyncio.run(engine.dispose())


def test_reader_filters_order_and_cursor_pagination(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.application.queries.logs import LogEventQuery
    from app.infrastructure.database.reader import SqlAlchemyLogEventReader

    url = database_url()
    monkeypatch.setenv("SENTINELSTREAM_DATABASE_URL", url)
    command.upgrade(alembic_config(), "head")
    engine = create_async_engine(url, pool_pre_ping=True)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    ids = [
        UUID(f"00000000-0000-4000-8000-{number:012d}") for number in range(7001, 7006)
    ]
    moments = [
        datetime(2026, 7, 22, 12, tzinfo=UTC),
        datetime(2026, 7, 22, 11, tzinfo=UTC),
        datetime(2026, 7, 22, 11, tzinfo=UTC),
        datetime(2026, 7, 22, 10, tzinfo=UTC),
        datetime(2026, 7, 22, 9, tzinfo=UTC),
    ]
    events = [
        LogEvent(
            event_id=ids[index],
            timestamp=moments[index],
            received_at=moments[index],
            service="payments-api" if index in (0, 2, 4) else "orders-api",
            environment="production" if index != 3 else "staging",
            level=LogLevel.ERROR if index in (0, 2, 3) else LogLevel.INFO,
            message=f"integration-{index}",
        )
        for index in range(5)
    ]

    async def scenario() -> None:
        repository = SqlAlchemyLogEventRepository(factory)
        reader = SqlAlchemyLogEventReader(factory)
        async with factory() as session:
            await session.execute(
                delete(LogEventRecord).where(LogEventRecord.event_id.in_(ids))
            )
            await session.commit()
        for event in events:
            await repository.add(event)
        first = await reader.list(LogEventQuery(limit=2))
        assert [item.event_id for item in first.items] == [
            ids[0],
            ids[2],
        ] and first.next_cursor is not None
        second = await reader.list(LogEventQuery(limit=2, cursor=first.next_cursor))
        assert [item.event_id for item in second.items] == [
            ids[1],
            ids[3],
        ] and second.next_cursor is not None
        final = await reader.list(LogEventQuery(limit=2, cursor=second.next_cursor))
        assert [item.event_id for item in final.items] == [
            ids[4]
        ] and final.next_cursor is None
        assert not (
            {item.event_id for item in first.items}
            & {item.event_id for item in second.items}
        )
        service = await reader.list(LogEventQuery(service="payments-api"))
        assert [item.event_id for item in service.items] == [ids[0], ids[2], ids[4]]
        environment = await reader.list(LogEventQuery(environment="staging"))
        assert [item.event_id for item in environment.items] == [ids[3]]
        level = await reader.list(LogEventQuery(level=LogLevel.ERROR))
        assert [item.event_id for item in level.items] == [ids[0], ids[2], ids[3]]
        inclusive = await reader.list(
            LogEventQuery(start_time=moments[1], end_time=moments[1])
        )
        assert [item.event_id for item in inclusive.items] == [ids[2], ids[1]]
        combined = await reader.list(
            LogEventQuery(
                service="payments-api",
                environment="production",
                level=LogLevel.ERROR,
                start_time=moments[2],
                end_time=moments[0],
            )
        )
        assert [item.event_id for item in combined.items] == [ids[0], ids[2]]
        async with factory() as session:
            await session.execute(
                delete(LogEventRecord).where(LogEventRecord.event_id.in_(ids))
            )
            await session.commit()

    try:
        asyncio.run(scenario())
    finally:
        asyncio.run(engine.dispose())


def test_anomaly_migration_atomic_persistence_uniqueness_and_cascade(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.application.anomalies import (
        RuleBasedAnomalyDetector,
        build_default_anomaly_rules,
    )
    from app.application.anomalies.policy import DetectionPolicy
    from app.domain.anomalies import AnomalyFinding, AnomalySeverity, AnomalyType
    from app.infrastructure.database.detection_persistence import (
        SqlAlchemyDetectionPersistence,
    )
    from app.infrastructure.database.models import AnomalyFindingRecord

    url = database_url()
    monkeypatch.setenv("SENTINELSTREAM_DATABASE_URL", url)
    command.upgrade(alembic_config(), "20260722_0001")
    command.upgrade(alembic_config(), "head")
    engine = create_async_engine(url, pool_pre_ping=True)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    normal_id = UUID("00000000-0000-4000-8000-000000009001")
    anomalous_id = UUID("00000000-0000-4000-8000-000000009002")
    failed_id = UUID("00000000-0000-4000-8000-000000009003")
    detector = RuleBasedAnomalyDetector(build_default_anomaly_rules(DetectionPolicy()))
    persistence = SqlAlchemyDetectionPersistence(factory)

    def make_event(event_id: UUID, *, anomalous: bool) -> LogEvent:
        return LogEvent(
            event_id=event_id,
            timestamp=datetime(2026, 7, 22, 12, tzinfo=UTC),
            received_at=datetime(2026, 7, 22, 12, 0, 1, tzinfo=UTC),
            service="day9-integration",
            environment="test",
            level=LogLevel.CRITICAL if anomalous else LogLevel.INFO,
            message="sensitive message",
            exception_type="TimeoutError" if anomalous else None,
            exception_message="secret exception text" if anomalous else None,
            status_code=575 if anomalous else 200,
            latency_ms=6000 if anomalous else 120,
            metadata={"secret": "metadata"},
        )

    async def scenario() -> None:
        ids = [normal_id, anomalous_id, failed_id]
        async with factory() as session:
            await session.execute(
                delete(LogEventRecord).where(LogEventRecord.event_id.in_(ids))
            )
            await session.commit()
        normal = make_event(normal_id, anomalous=False)
        normal_result = detector.detect(normal)
        await persistence.persist(normal, normal_result.findings)
        anomalous = make_event(anomalous_id, anomalous=True)
        anomalous_result = detector.detect(anomalous)
        await persistence.persist(anomalous, anomalous_result.findings)
        async with factory() as session:
            normal_count = await session.scalar(
                select(func.count())
                .select_from(AnomalyFindingRecord)
                .where(AnomalyFindingRecord.event_id == normal_id)
            )
            records = list(
                (
                    await session.scalars(
                        select(AnomalyFindingRecord)
                        .where(AnomalyFindingRecord.event_id == anomalous_id)
                        .order_by(
                            AnomalyFindingRecord.created_at, AnomalyFindingRecord.id
                        )
                    )
                ).all()
            )
        assert normal_count == 0
        assert {record.rule_id for record in records} == {
            finding.rule_id for finding in anomalous_result.findings
        }
        assert {record.anomaly_type for record in records} == {
            finding.anomaly_type.value for finding in anomalous_result.findings
        }
        assert all(isinstance(record.evidence, list) for record in records)
        assert all(
            "secret exception text" not in " ".join(record.evidence)
            for record in records
        )
        duplicate = AnomalyFinding(
            AnomalyType.ERROR_LEVEL,
            AnomalySeverity.HIGH,
            "duplicate.rule.v1",
            "Duplicate",
            ("level=error",),
        )
        failed_event = make_event(failed_id, anomalous=False)
        with pytest.raises(IntegrityError):
            await persistence.persist(failed_event, (duplicate, duplicate))
        async with factory() as session:
            assert await session.get(LogEventRecord, failed_id) is None
            failed_findings = await session.scalar(
                select(func.count())
                .select_from(AnomalyFindingRecord)
                .where(AnomalyFindingRecord.event_id == failed_id)
            )
            assert failed_findings == 0
        with pytest.raises(IntegrityError):
            await persistence.persist(anomalous, anomalous_result.findings)
        async with factory() as session:
            count_after_reprocess = await session.scalar(
                select(func.count())
                .select_from(AnomalyFindingRecord)
                .where(AnomalyFindingRecord.event_id == anomalous_id)
            )
            assert count_after_reprocess == 4
            await session.execute(
                delete(LogEventRecord).where(LogEventRecord.event_id == anomalous_id)
            )
            await session.commit()
        async with factory() as session:
            assert (
                await session.scalar(
                    select(func.count())
                    .select_from(AnomalyFindingRecord)
                    .where(AnomalyFindingRecord.event_id == anomalous_id)
                )
                == 0
            )

    async def anomaly_table_exists() -> bool:
        async with engine.connect() as connection:
            return await connection.run_sync(
                lambda sync: inspect(sync).has_table("anomaly_findings")
            )

    async def log_table_and_normal_row_exist() -> tuple[bool, bool]:
        async with engine.connect() as connection:
            table_exists = await connection.run_sync(
                lambda sync: inspect(sync).has_table("log_events")
            )
        async with factory() as session:
            row_exists = await session.get(LogEventRecord, normal_id) is not None
        return table_exists, row_exists

    try:
        assert asyncio.run(anomaly_table_exists())
        asyncio.run(scenario())
        command.downgrade(alembic_config(), "20260722_0001")
        assert not asyncio.run(anomaly_table_exists())
        assert asyncio.run(log_table_and_normal_row_exist()) == (True, True)
        command.upgrade(alembic_config(), "head")
        assert asyncio.run(anomaly_table_exists())
        asyncio.run(_cleanup_day9_rows(factory, [normal_id, anomalous_id, failed_id]))
    finally:
        asyncio.run(engine.dispose())


async def _cleanup_day9_rows(
    factory: async_sessionmaker[AsyncSession], event_ids: list[UUID]
) -> None:
    async with factory() as session:
        await session.execute(
            delete(LogEventRecord).where(LogEventRecord.event_id.in_(event_ids))
        )
        await session.commit()


def test_anomaly_reader_filters_order_and_cursor_pagination(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.application.queries.anomalies import AnomalyFindingQuery
    from app.domain.anomalies import AnomalySeverity, AnomalyType
    from app.infrastructure.database.anomaly_reader import (
        SqlAlchemyAnomalyFindingReader,
    )
    from app.infrastructure.database.mapper import map_log_event
    from app.infrastructure.database.models import AnomalyFindingRecord

    url = database_url()
    monkeypatch.setenv("SENTINELSTREAM_DATABASE_URL", url)
    command.upgrade(alembic_config(), "head")
    engine = create_async_engine(url, pool_pre_ping=True)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    event_ids = [UUID(int=9201), UUID(int=9202)]
    finding_ids = [UUID(int=9300 + number) for number in range(1, 7)]
    moments = [
        datetime(2026, 7, 22, 12, tzinfo=UTC),
        datetime(2026, 7, 22, 11, tzinfo=UTC),
        datetime(2026, 7, 22, 11, tzinfo=UTC),
        datetime(2026, 7, 22, 10, tzinfo=UTC),
        datetime(2026, 7, 22, 9, tzinfo=UTC),
        datetime(2026, 7, 22, 8, tzinfo=UTC),
    ]
    events = [
        LogEvent(
            event_id=event_id,
            timestamp=moments[0],
            received_at=moments[0],
            service="day10-reader",
            environment="test",
            level=LogLevel.INFO,
            message="integration source",
        )
        for event_id in event_ids
    ]
    records = [
        AnomalyFindingRecord(
            id=finding_ids[index],
            event_id=event_ids[index % 2],
            anomaly_type=("high_latency" if index < 4 else "error_level"),
            severity=("critical" if index % 2 == 0 else "high"),
            rule_id=f"day10.rule.{index}.v1",
            title="Day 10 finding",
            evidence=[f"index={index}"],
            created_at=moments[index],
        )
        for index in range(6)
    ]

    async def scenario() -> None:
        async with factory() as session:
            await session.execute(
                delete(LogEventRecord).where(LogEventRecord.event_id.in_(event_ids))
            )
            session.add_all([map_log_event(event) for event in events])
            await session.flush()
            session.add_all(records)
            await session.commit()
        reader = SqlAlchemyAnomalyFindingReader(factory)
        first = await reader.list(AnomalyFindingQuery(limit=2))
        second = await reader.list(
            AnomalyFindingQuery(limit=2, cursor=first.next_cursor)
        )
        third = await reader.list(
            AnomalyFindingQuery(limit=2, cursor=second.next_cursor)
        )
        traversed = [item.id for page in (first, second, third) for item in page.items]
        assert traversed == [
            finding_ids[0],
            finding_ids[2],
            finding_ids[1],
            finding_ids[3],
            finding_ids[4],
            finding_ids[5],
        ]
        assert len(set(traversed)) == 6 and third.next_cursor is None
        by_event = await reader.list(AnomalyFindingQuery(event_id=event_ids[0]))
        assert {item.event_id for item in by_event.items} == {event_ids[0]}
        by_type = await reader.list(
            AnomalyFindingQuery(anomaly_type=AnomalyType.HIGH_LATENCY)
        )
        assert len(by_type.items) == 4
        by_severity = await reader.list(
            AnomalyFindingQuery(severity=AnomalySeverity.CRITICAL)
        )
        assert len(by_severity.items) == 3
        by_rule = await reader.list(AnomalyFindingQuery(rule_id="day10.rule.3.v1"))
        assert [item.id for item in by_rule.items] == [finding_ids[3]]
        inclusive = await reader.list(
            AnomalyFindingQuery(start_time=moments[1], end_time=moments[1])
        )
        assert [item.id for item in inclusive.items] == [finding_ids[2], finding_ids[1]]
        combined = await reader.list(
            AnomalyFindingQuery(
                event_id=event_ids[0],
                anomaly_type=AnomalyType.HIGH_LATENCY,
                severity=AnomalySeverity.CRITICAL,
                start_time=moments[2],
                end_time=moments[0],
            )
        )
        assert [item.id for item in combined.items] == [finding_ids[0], finding_ids[2]]
        async with factory() as session:
            await session.execute(
                delete(LogEventRecord).where(LogEventRecord.event_id.in_(event_ids))
            )
            await session.commit()

    try:
        asyncio.run(scenario())
    finally:
        asyncio.run(engine.dispose())


def test_incident_migration_persistence_idempotency_constraints_and_downgrade(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.application.incidents.exceptions import IncidentFindingAlreadyAssignedError
    from app.application.incidents.identity import build_incident_id
    from app.domain.anomalies import AnomalySeverity, AnomalyType
    from app.domain.incidents import IncidentCandidate, IncidentGroupingKey
    from app.infrastructure.database.incident_persistence import (
        SqlAlchemyIncidentPersistence,
    )
    from app.infrastructure.database.models import (
        AnomalyFindingRecord,
        IncidentFindingRecord,
        IncidentRecord,
    )

    url = database_url()
    monkeypatch.setenv("SENTINELSTREAM_DATABASE_URL", url)
    command.upgrade(alembic_config(), "head")
    engine = create_async_engine(url, pool_pre_ping=True)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    event_id = UUID(int=12001)
    finding_ids = (UUID(int=12101), UUID(int=12102), UUID(int=12103))
    moment = datetime(2026, 7, 22, 12, tzinfo=UTC)
    candidate = IncidentCandidate(
        key=IncidentGroupingKey("day12", "test", AnomalyType.HIGH_LATENCY),
        finding_ids=finding_ids,
        event_ids=(event_id, event_id, event_id),
        rule_ids=("day12.one.v1", "day12.two.v1", "day12.three.v1"),
        started_at=moment,
        last_seen_at=moment,
        finding_count=3,
        highest_severity=AnomalySeverity.CRITICAL,
    )

    async def prepare_and_persist() -> None:
        async with factory() as session:
            await session.execute(
                delete(LogEventRecord).where(LogEventRecord.event_id == event_id)
            )
            session.add(
                LogEventRecord(
                    event_id=event_id,
                    timestamp=moment,
                    received_at=moment,
                    service="day12",
                    environment="test",
                    level="ERROR",
                    message="source",
                    exception_type=None,
                    exception_message=None,
                    latency_ms=None,
                    status_code=None,
                    trace_id=None,
                    request_id=None,
                    host=None,
                    event_metadata={},
                )
            )
            await session.flush()
            session.add_all(
                [
                    AnomalyFindingRecord(
                        id=finding_id,
                        event_id=event_id,
                        anomaly_type="high_latency",
                        severity="critical",
                        rule_id=f"day12.{index}.v1",
                        title="Finding",
                        evidence=[f"index={index}"],
                        created_at=moment,
                    )
                    for index, finding_id in enumerate(finding_ids)
                ]
            )
            await session.commit()
        persistence = SqlAlchemyIncidentPersistence(factory)
        first = await persistence.persist(candidate)
        second = await persistence.persist(candidate)
        assert first == second == build_incident_id(candidate)
        async with factory() as session:
            assert (
                await session.scalar(select(func.count()).select_from(IncidentRecord))
                == 1
            )
            memberships = list(
                (
                    await session.scalars(
                        select(IncidentFindingRecord)
                        .where(IncidentFindingRecord.incident_id == first)
                        .order_by(IncidentFindingRecord.position)
                    )
                ).all()
            )
            assert [(row.finding_id, row.position) for row in memberships] == list(
                zip(finding_ids, range(3), strict=True)
            )
        conflict = IncidentCandidate(
            key=IncidentGroupingKey("other", "test", AnomalyType.HIGH_LATENCY),
            finding_ids=(finding_ids[0], UUID(int=12104)),
            event_ids=(event_id, event_id),
            rule_ids=("other.one", "other.two"),
            started_at=moment,
            last_seen_at=moment,
            finding_count=2,
            highest_severity=AnomalySeverity.HIGH,
        )
        async with factory() as session:
            session.add(
                AnomalyFindingRecord(
                    id=UUID(int=12104),
                    event_id=event_id,
                    anomaly_type="high_latency",
                    severity="high",
                    rule_id="day12.4.v1",
                    title="Finding",
                    evidence=["index=4"],
                    created_at=moment,
                )
            )
            await session.commit()
        with pytest.raises(IncidentFindingAlreadyAssignedError):
            await persistence.persist(conflict)
        async with factory() as session:
            assert (
                await session.get(IncidentRecord, build_incident_id(conflict)) is None
            )
            await session.execute(
                delete(IncidentRecord).where(IncidentRecord.id == first)
            )
            await session.commit()
            assert (
                await session.scalar(
                    select(func.count()).select_from(IncidentFindingRecord)
                )
                == 0
            )

    async def table_state() -> tuple[bool, bool, bool, bool]:
        async with engine.connect() as connection:
            return await connection.run_sync(
                lambda sync: (
                    inspect(sync).has_table("incidents"),
                    inspect(sync).has_table("incident_findings"),
                    inspect(sync).has_table("log_events"),
                    inspect(sync).has_table("anomaly_findings"),
                )
            )

    async def cleanup() -> None:
        async with factory() as session:
            await session.execute(
                delete(LogEventRecord).where(LogEventRecord.event_id == event_id)
            )
            await session.commit()

    try:
        asyncio.run(prepare_and_persist())
        command.downgrade(alembic_config(), "20260722_0002")
        assert asyncio.run(table_state()) == (False, False, True, True)
        command.upgrade(alembic_config(), "head")
        assert asyncio.run(table_state()) == (True, True, True, True)
        asyncio.run(cleanup())
    finally:
        asyncio.run(engine.dispose())


def test_incident_reader_order_filters_pagination_and_detail(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from datetime import timedelta

    from app.application.queries.incidents import IncidentQuery
    from app.domain.anomalies import AnomalySeverity, AnomalyType
    from app.infrastructure.database.incident_reader import SqlAlchemyIncidentReader
    from app.infrastructure.database.models import (
        AnomalyFindingRecord,
        IncidentFindingRecord,
        IncidentRecord,
    )

    url = database_url()
    monkeypatch.setenv("SENTINELSTREAM_DATABASE_URL", url)
    command.upgrade(alembic_config(), "head")
    engine = create_async_engine(url, pool_pre_ping=True)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    base = datetime(2026, 7, 22, 15, tzinfo=UTC)
    event_ids = tuple(UUID(int=13000 + index) for index in range(6))
    incident_ids = tuple(UUID(int=13100 + index) for index in range(3))
    finding_ids = tuple(UUID(int=13200 + index) for index in range(6))

    async def scenario() -> None:
        async with factory() as session:
            session.add_all(
                [
                    LogEventRecord(
                        event_id=event_id,
                        timestamp=base,
                        received_at=base,
                        service="day13",
                        environment="test",
                        level="ERROR",
                        message="private source",
                        exception_type=None,
                        exception_message=None,
                        latency_ms=None,
                        status_code=None,
                        trace_id=None,
                        request_id=None,
                        host=None,
                        event_metadata={"private": True},
                    )
                    for event_id in event_ids
                ]
            )
            await session.flush()
            session.add_all(
                [
                    AnomalyFindingRecord(
                        id=finding_ids[index],
                        event_id=event_ids[index],
                        anomaly_type="high_latency",
                        severity=("critical", "high", "medium")[index // 2],
                        rule_id=f"day13.{index}.v1",
                        title="Safe finding",
                        evidence=[f"index={index}"],
                        created_at=base,
                    )
                    for index in range(6)
                ]
            )
            await session.flush()
            for index, incident_id in enumerate(incident_ids):
                seen = base - timedelta(minutes=index * 5)
                session.add(
                    IncidentRecord(
                        id=incident_id,
                        service=("payments", "payments", "catalog")[index],
                        environment=("prod", "test", "prod")[index],
                        anomaly_type="high_latency",
                        started_at=seen - timedelta(minutes=1),
                        last_seen_at=seen,
                        finding_count=2,
                        highest_severity=("critical", "high", "medium")[index],
                        created_at=base,
                    )
                )
                await session.flush()
                session.add_all(
                    [
                        IncidentFindingRecord(
                            incident_id=incident_id,
                            finding_id=finding_ids[index * 2 + position],
                            position=position,
                            created_at=base,
                        )
                        for position in range(2)
                    ]
                )
            await session.commit()

        reader = SqlAlchemyIncidentReader(factory)
        first = await reader.list(IncidentQuery(limit=1))
        second = await reader.list(IncidentQuery(limit=1, cursor=first.next_cursor))
        third = await reader.list(IncidentQuery(limit=1, cursor=second.next_cursor))
        assert [first.items[0].id, second.items[0].id, third.items[0].id] == list(
            incident_ids
        )
        assert third.next_cursor is None
        assert [
            item.id
            for item in (await reader.list(IncidentQuery(service="payments"))).items
        ] == list(incident_ids[:2])
        assert [
            item.id
            for item in (await reader.list(IncidentQuery(environment="test"))).items
        ] == [incident_ids[1]]
        assert [
            item.id
            for item in (
                await reader.list(
                    IncidentQuery(
                        anomaly_type=AnomalyType.HIGH_LATENCY,
                        highest_severity=AnomalySeverity.CRITICAL,
                    )
                )
            ).items
        ] == [incident_ids[0]]
        assert (
            len(
                (
                    await reader.list(
                        IncidentQuery(
                            started_after=base - timedelta(minutes=6),
                            last_seen_before=base,
                            minimum_finding_count=2,
                        )
                    )
                ).items
            )
            == 2
        )
        detail = await reader.get(incident_ids[0])
        assert detail is not None
        assert [item.position for item in detail.findings] == [0, 1]
        assert [item.event_id for item in detail.findings] == list(event_ids[:2])
        assert await reader.get(UUID(int=13999)) is None

        async with factory() as session:
            await session.execute(
                delete(LogEventRecord).where(LogEventRecord.event_id.in_(event_ids))
            )
            await session.commit()

    try:
        asyncio.run(scenario())
    finally:
        asyncio.run(engine.dispose())
