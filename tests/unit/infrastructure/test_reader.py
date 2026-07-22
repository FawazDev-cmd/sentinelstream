import asyncio
from datetime import UTC, datetime
from typing import Any, cast
from uuid import UUID

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.sql import Select

from app.application.queries.logs import LogEventCursor, LogEventQuery
from app.domain.logs import LogEvent, LogLevel
from app.infrastructure.database.mapper import map_log_event
from app.infrastructure.database.models import LogEventRecord
from app.infrastructure.database.reader import SqlAlchemyLogEventReader


class Result:
    def __init__(self, rows: list[LogEventRecord]) -> None:
        self.rows = rows

    def all(self) -> list[LogEventRecord]:
        return self.rows


class FakeSession:
    def __init__(
        self, rows: list[LogEventRecord], failure: BaseException | None = None
    ) -> None:
        self.rows = rows
        self.failure = failure
        self.statement: Select[Any] | None = None
        self.entered = False
        self.exited = False

    async def __aenter__(self) -> "FakeSession":
        self.entered = True
        return self

    async def __aexit__(self, *args: object) -> None:
        self.exited = True

    async def scalars(self, statement: Select[Any]) -> Result:
        self.statement = statement
        if self.failure is not None:
            raise self.failure
        return Result(self.rows)


class Factory:
    def __init__(
        self, rows: list[LogEventRecord], failure: BaseException | None = None
    ) -> None:
        self.rows = rows
        self.failure = failure
        self.sessions: list[FakeSession] = []

    def __call__(self) -> FakeSession:
        session = FakeSession(self.rows, self.failure)
        self.sessions.append(session)
        return session


def reader(factory: Factory) -> SqlAlchemyLogEventReader:
    return SqlAlchemyLogEventReader(
        cast(async_sessionmaker[AsyncSession], cast(Any, factory))
    )


def record(number: int, timestamp: datetime | None = None) -> LogEventRecord:
    event = LogEvent(
        event_id=UUID(int=number),
        timestamp=timestamp or datetime(2026, 7, 22, 10, tzinfo=UTC),
        received_at=datetime(2026, 7, 22, 11, tzinfo=UTC),
        service="api",
        environment="test",
        level=LogLevel.ERROR,
        message=f"event-{number}",
    )
    return map_log_event(event)


def test_reader_uses_fresh_closed_sessions_and_no_commit() -> None:
    async def scenario() -> None:
        factory = Factory([])
        adapter = reader(factory)
        await adapter.list(LogEventQuery())
        await adapter.list(LogEventQuery())
        assert (
            len(factory.sessions) == 2
            and factory.sessions[0] is not factory.sessions[1]
        )
        assert all(session.entered and session.exited for session in factory.sessions)
        assert all(not hasattr(session, "commit") for session in factory.sessions)

    asyncio.run(scenario())


def test_statement_applies_all_filters_cursor_order_and_lookahead() -> None:
    async def scenario() -> None:
        moment = datetime(2026, 7, 22, 10, tzinfo=UTC)
        factory = Factory([])
        query = LogEventQuery(
            service="api",
            environment="test",
            level=LogLevel.ERROR,
            start_time=moment,
            end_time=moment,
            limit=10,
            cursor=LogEventCursor(moment, UUID(int=9)),
        )
        await reader(factory).list(query)
        statement = factory.sessions[0].statement
        assert statement is not None
        sql = str(statement)
        assert (
            "log_events.service =" in sql
            and "log_events.environment =" in sql
            and "log_events.level =" in sql
        )
        assert "log_events.timestamp >=" in sql and "log_events.timestamp <=" in sql
        assert (
            "log_events.timestamp <" in sql
            and "log_events.event_id <" in sql
            and " OR " in sql
        )
        assert "ORDER BY log_events.timestamp DESC, log_events.event_id DESC" in sql
        assert (
            statement._limit_clause is not None and statement._limit_clause.value == 11
        )

    asyncio.run(scenario())


def test_page_lookahead_and_cursor_use_last_returned_item() -> None:
    async def scenario() -> None:
        rows = [record(3), record(2), record(1)]
        page = await reader(Factory(rows)).list(LogEventQuery(limit=2))
        assert [event.event_id.int for event in page.items] == [3, 2]
        assert page.next_cursor == LogEventCursor(rows[1].timestamp, rows[1].event_id)

    asyncio.run(scenario())


def test_final_page_has_no_cursor() -> None:
    page = asyncio.run(reader(Factory([record(1)])).list(LogEventQuery(limit=2)))
    assert len(page.items) == 1 and page.next_cursor is None


@pytest.mark.parametrize(
    "failure", [RuntimeError("database failed"), asyncio.CancelledError()]
)
def test_reader_errors_and_cancellation_propagate(failure: BaseException) -> None:
    async def scenario() -> None:
        with pytest.raises(type(failure)):
            await reader(Factory([], failure)).list(LogEventQuery())

    asyncio.run(scenario())
