"""PostgreSQL integration tests enabled by SENTINELSTREAM_TEST_DATABASE_URL."""

import asyncio
import os
from datetime import UTC, datetime
from uuid import UUID

import pytest
from sqlalchemy import delete, select
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.domain.logs import LogEvent, LogLevel
from app.infrastructure.database.models import LogEventRecord
from app.infrastructure.database.repository import SqlAlchemyLogEventRepository
from app.infrastructure.database.schema import create_database_schema

pytestmark = pytest.mark.integration


def database_url() -> str:
    value = os.getenv("SENTINELSTREAM_TEST_DATABASE_URL")
    if not value:
        pytest.skip("SENTINELSTREAM_TEST_DATABASE_URL is not configured")
    database = make_url(value).database or ""
    if "test" not in database.casefold():
        pytest.fail("integration database name must contain 'test'")
    return value


def test_postgresql_schema_insert_duplicate_and_non_destructive_create() -> None:
    async def scenario() -> None:
        engine = create_async_engine(database_url(), pool_pre_ping=True)
        factory = async_sessionmaker(engine, expire_on_commit=False)
        repository = SqlAlchemyLogEventRepository(factory)
        first_id = UUID("00000000-0000-4000-8000-000000005001")
        second_id = UUID("00000000-0000-4000-8000-000000005002")
        try:
            await create_database_schema(engine)
            async with factory() as session:
                await session.execute(
                    delete(LogEventRecord).where(
                        LogEventRecord.event_id.in_([first_id, second_id])
                    )
                )
                await session.commit()
            complete = LogEvent(
                event_id=first_id,
                timestamp=datetime(2026, 7, 22, 10, tzinfo=UTC),
                received_at=datetime(2026, 7, 22, 10, 0, 1, tzinfo=UTC),
                service="integration-api",
                environment="test",
                level=LogLevel.ERROR,
                message="failure",
                latency_ms=12.5,
                status_code=500,
                metadata={"source": "integration", "items": [1, True]},  # type: ignore[dict-item]
            )
            minimal = LogEvent(
                event_id=second_id,
                timestamp=datetime(2026, 7, 22, 11, tzinfo=UTC),
                received_at=datetime(2026, 7, 22, 11, 0, 1, tzinfo=UTC),
                service="integration-api",
                environment="test",
                level=LogLevel.INFO,
                message="ok",
            )
            await repository.add(complete)
            await create_database_schema(engine)
            await repository.add(minimal)
            async with factory() as session:
                rows = (
                    await session.scalars(
                        select(LogEventRecord).where(
                            LogEventRecord.event_id.in_([first_id, second_id])
                        )
                    )
                ).all()
            by_id = {row.event_id: row for row in rows}
            assert set(by_id) == {first_id, second_id}
            stored = by_id[first_id]
            assert stored.timestamp.astimezone(UTC) == complete.timestamp
            assert stored.received_at.astimezone(UTC) == complete.received_at
            assert stored.level == "ERROR" and stored.event_metadata == {
                "source": "integration",
                "items": [1, True],
            }
            assert by_id[second_id].exception_type is None
            with pytest.raises(IntegrityError):
                await repository.add(complete)
            third = LogEvent(
                event_id=UUID("00000000-0000-4000-8000-000000005003"),
                timestamp=datetime(2026, 7, 22, 12, tzinfo=UTC),
                received_at=datetime(2026, 7, 22, 12, tzinfo=UTC),
                service="integration-api",
                environment="test",
                level=LogLevel.INFO,
                message="after duplicate",
            )
            await repository.add(third)
            async with factory() as session:
                await session.execute(
                    delete(LogEventRecord).where(
                        LogEventRecord.event_id.in_(
                            [first_id, second_id, third.event_id]
                        )
                    )
                )
                await session.commit()
        finally:
            await engine.dispose()

    asyncio.run(scenario())
