import asyncio
from collections.abc import Callable
from typing import Any, cast

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.infrastructure.database.models import LogEventRecord
from app.infrastructure.database.repository import SqlAlchemyLogEventRepository
from tests.unit.infrastructure.test_models import complete_event


class FakeSession:
    def __init__(self, failure: BaseException | None = None) -> None:
        self.failure = failure
        self.added: list[object] = []
        self.commits = 0
        self.rollbacks = 0
        self.entered = False
        self.exited = False

    async def __aenter__(self) -> "FakeSession":
        self.entered = True
        return self

    async def __aexit__(self, *args: object) -> None:
        self.exited = True

    def add(self, value: object) -> None:
        self.added.append(value)

    async def commit(self) -> None:
        self.commits += 1
        if self.failure is not None:
            raise self.failure

    async def rollback(self) -> None:
        self.rollbacks += 1


class FakeFactory:
    def __init__(self, builder: Callable[[], FakeSession]) -> None:
        self.builder = builder
        self.sessions: list[FakeSession] = []

    def __call__(self) -> FakeSession:
        session = self.builder()
        self.sessions.append(session)
        return session


def repository(factory: FakeFactory) -> SqlAlchemyLogEventRepository:
    return SqlAlchemyLogEventRepository(
        cast(async_sessionmaker[AsyncSession], cast(Any, factory))
    )


def test_repository_adds_commits_and_uses_fresh_closed_sessions() -> None:
    async def scenario() -> None:
        factory = FakeFactory(FakeSession)
        repo = repository(factory)
        event = complete_event()
        await repo.add(event)
        await repo.add(event)
        assert (
            len(factory.sessions) == 2
            and factory.sessions[0] is not factory.sessions[1]
        )
        for session in factory.sessions:
            assert session.entered and session.exited
            assert session.commits == 1 and session.rollbacks == 0
            assert len(session.added) == 1 and isinstance(
                session.added[0], LogEventRecord
            )

    asyncio.run(scenario())


def test_commit_failure_rolls_back_propagates_and_does_not_retry() -> None:
    async def scenario() -> None:
        failure = RuntimeError("database failure")
        factory = FakeFactory(lambda: FakeSession(failure))
        repo = repository(factory)
        with pytest.raises(RuntimeError, match="database failure"):
            await repo.add(complete_event())
        assert len(factory.sessions) == 1
        assert factory.sessions[0].commits == 1 and factory.sessions[0].rollbacks == 1
        assert factory.sessions[0].exited

    asyncio.run(scenario())


def test_cancellation_is_not_converted_to_success() -> None:
    async def scenario() -> None:
        factory = FakeFactory(lambda: FakeSession(asyncio.CancelledError()))
        repo = repository(factory)
        with pytest.raises(asyncio.CancelledError):
            await repo.add(complete_event())
        assert len(factory.sessions) == 1 and factory.sessions[0].exited

    asyncio.run(scenario())
