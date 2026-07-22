"""Guarded PostgreSQL migration integration test."""

import asyncio
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import cast
from uuid import UUID

import pytest
from alembic.config import Config
from sqlalchemy import Table, delete, inspect, text
from sqlalchemy.engine import make_url
from sqlalchemy.engine.reflection import Inspector
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from alembic import command
from app.domain.logs import LogEvent, LogLevel
from app.infrastructure.database.models import LogEventRecord
from app.infrastructure.database.repository import SqlAlchemyLogEventRepository

pytestmark = pytest.mark.integration
ROOT = Path(__file__).parents[2]
REVISION = "20260722_0001"
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
