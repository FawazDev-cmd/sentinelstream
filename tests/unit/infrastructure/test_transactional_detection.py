"""Tests for one-session transactional event-and-finding persistence."""

import asyncio
from collections.abc import Callable
from typing import Any, cast

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.application.contracts.clock import Clock
from app.domain.anomalies import AnomalyFinding, AnomalySeverity, AnomalyType
from app.infrastructure.database.detection_persistence import (
    SqlAlchemyDetectionPersistence,
)
from app.infrastructure.database.models import AnomalyFindingRecord, LogEventRecord
from tests.unit.infrastructure.test_models import complete_event


class FixedClock(Clock):
    def now(self) -> Any:
        return complete_event().received_at


class FakeTransaction:
    def __init__(self, session: "FakeSession") -> None:
        self.session = session

    async def __aenter__(self) -> "FakeTransaction":
        self.session.transactions += 1
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: object,
    ) -> None:
        if exc_type is None:
            self.session.commits += 1
        else:
            self.session.rollbacks += 1


class FakeSession:
    def __init__(
        self,
        event_failure: BaseException | None = None,
        finding_failure: BaseException | None = None,
    ) -> None:
        self.event_failure = event_failure
        self.finding_failure = finding_failure
        self.added: list[object] = []
        self.transactions = 0
        self.commits = 0
        self.rollbacks = 0
        self.flushes = 0
        self.entered = False
        self.closed = False

    async def __aenter__(self) -> "FakeSession":
        self.entered = True
        return self

    async def __aexit__(self, *args: object) -> None:
        self.closed = True

    def begin(self) -> FakeTransaction:
        return FakeTransaction(self)

    def add(self, record: object) -> None:
        if self.event_failure is not None:
            raise self.event_failure
        self.added.append(record)

    async def flush(self) -> None:
        self.flushes += 1

    def add_all(self, records: list[object]) -> None:
        if self.finding_failure is not None:
            raise self.finding_failure
        self.added.extend(records)


class FakeFactory:
    def __init__(self, builder: Callable[[], FakeSession]) -> None:
        self.builder = builder
        self.sessions: list[FakeSession] = []

    def __call__(self) -> FakeSession:
        session = self.builder()
        self.sessions.append(session)
        return session


def persistence(factory: FakeFactory) -> SqlAlchemyDetectionPersistence:
    return SqlAlchemyDetectionPersistence(
        cast(async_sessionmaker[AsyncSession], cast(Any, factory)), FixedClock()
    )


def finding(rule_id: str = "rule.v1") -> AnomalyFinding:
    return AnomalyFinding(
        AnomalyType.ERROR_LEVEL,
        AnomalySeverity.HIGH,
        rule_id,
        "Finding",
        ("level=error",),
    )


def test_fresh_session_one_transaction_event_first_and_all_findings_same_session() -> (
    None
):
    async def scenario() -> None:
        factory = FakeFactory(FakeSession)
        store = persistence(factory)
        findings = (finding("one"), finding("two"))
        await store.persist(complete_event(), findings)
        await store.persist(complete_event(), ())
        assert (
            len(factory.sessions) == 2
            and factory.sessions[0] is not factory.sessions[1]
        )
        first, second = factory.sessions
        assert isinstance(first.added[0], LogEventRecord)
        assert all(isinstance(item, AnomalyFindingRecord) for item in first.added[1:])
        assert [item.rule_id for item in first.added[1:]] == ["one", "two"]  # type: ignore[attr-defined]
        for session in (first, second):
            assert session.entered and session.closed
            assert session.transactions == 1 and session.commits == 1
            assert session.rollbacks == 0 and session.flushes == 1
        assert second.added and isinstance(second.added[0], LogEventRecord)
        assert len(second.added) == 1

    asyncio.run(scenario())


@pytest.mark.parametrize("stage", ["event", "finding"])
def test_any_insertion_failure_rolls_back_and_closes(stage: str) -> None:
    async def scenario() -> None:
        failure = RuntimeError(f"{stage} failed")
        factory = FakeFactory(
            lambda: FakeSession(
                event_failure=failure if stage == "event" else None,
                finding_failure=failure if stage == "finding" else None,
            )
        )
        with pytest.raises(RuntimeError, match=f"{stage} failed"):
            await persistence(factory).persist(complete_event(), (finding(),))
        session = factory.sessions[0]
        assert session.closed and session.commits == 0 and session.rollbacks == 1
        if stage == "event":
            assert session.added == [] and session.flushes == 0
        else:
            assert len(session.added) == 1 and isinstance(
                session.added[0], LogEventRecord
            )

    asyncio.run(scenario())


def test_cancellation_rolls_back_closes_and_propagates() -> None:
    async def scenario() -> None:
        factory = FakeFactory(
            lambda: FakeSession(finding_failure=asyncio.CancelledError())
        )
        with pytest.raises(asyncio.CancelledError):
            await persistence(factory).persist(complete_event(), (finding(),))
        session = factory.sessions[0]
        assert session.closed and session.rollbacks == 1 and session.commits == 0

    asyncio.run(scenario())


def test_transactional_persistence_has_no_engine_to_dispose_per_request() -> None:
    store = persistence(FakeFactory(FakeSession))
    assert not hasattr(store, "dispose") and not hasattr(store, "engine")
