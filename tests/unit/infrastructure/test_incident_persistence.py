"""Tests for transactional idempotent incident persistence."""

import asyncio
from datetime import datetime
from typing import Any, cast
from uuid import UUID

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.application.contracts.clock import Clock
from app.application.incidents.exceptions import (
    IncidentFindingAlreadyAssignedError,
    IncidentPersistenceConflictError,
)
from app.application.incidents.identity import build_incident_id
from app.application.incidents.persistence import IncidentPersistence
from app.infrastructure.database.incident_persistence import (
    SqlAlchemyIncidentPersistence,
)
from app.infrastructure.database.models import IncidentFindingRecord, IncidentRecord
from tests.unit.application.incidents.test_identity import BASE, candidate


class FixedClock(Clock):
    def now(self) -> datetime:
        return BASE.replace(hour=13)


class Store:
    def __init__(self) -> None:
        self.incidents: dict[UUID, IncidentRecord] = {}
        self.memberships: dict[UUID, list[IncidentFindingRecord]] = {}


class Result:
    def __init__(self, rows: list[IncidentFindingRecord]) -> None:
        self.rows = rows

    def all(self) -> list[IncidentFindingRecord]:
        return self.rows


class Transaction:
    def __init__(self, session: "Session") -> None:
        self.session = session

    async def __aenter__(self) -> "Transaction":
        self.session.transactions += 1
        return self

    async def __aexit__(self, exc_type: object, exc: object, traceback: object) -> None:
        if exc_type is None:
            self.session.commits += 1
            if self.session.pending_incident is not None:
                record = self.session.pending_incident
                self.session.store.incidents[record.id] = record
                self.session.store.memberships[record.id] = list(
                    self.session.pending_memberships
                )
        else:
            self.session.rollbacks += 1


class Session:
    def __init__(
        self,
        store: Store,
        *,
        incident_failure: BaseException | None = None,
        membership_failure_after: int | None = None,
    ) -> None:
        self.store = store
        self.incident_failure = incident_failure
        self.membership_failure_after = membership_failure_after
        self.pending_incident: IncidentRecord | None = None
        self.pending_memberships: list[IncidentFindingRecord] = []
        self.transactions = self.commits = self.rollbacks = self.flushes = 0
        self.entered = self.closed = False

    async def __aenter__(self) -> "Session":
        self.entered = True
        return self

    async def __aexit__(self, *args: object) -> None:
        self.closed = True

    def begin(self) -> Transaction:
        return Transaction(self)

    async def get(self, model: object, identity: UUID) -> IncidentRecord | None:
        return self.store.incidents.get(identity)

    async def scalars(self, statement: object) -> Result:
        assert self.store.incidents
        incident_id = next(iter(self.store.incidents))
        rows = sorted(
            self.store.memberships.get(incident_id, []), key=lambda row: row.position
        )
        return Result(rows)

    def add(self, record: IncidentRecord) -> None:
        if self.incident_failure is not None:
            raise self.incident_failure
        self.pending_incident = record

    async def flush(self) -> None:
        self.flushes += 1

    def add_all(self, rows: list[IncidentFindingRecord]) -> None:
        for index, row in enumerate(rows):
            if (
                self.membership_failure_after is not None
                and index >= self.membership_failure_after
            ):
                raise IntegrityError("membership conflict", {}, Exception("assigned"))
            self.pending_memberships.append(row)


class Factory:
    def __init__(self, store: Store, **session_options: object) -> None:
        self.store = store
        self.session_options = session_options
        self.sessions: list[Session] = []

    def __call__(self) -> Session:
        session = Session(self.store, **self.session_options)  # type: ignore[arg-type]
        self.sessions.append(session)
        return session


def adapter(factory: Factory) -> SqlAlchemyIncidentPersistence:
    return SqlAlchemyIncidentPersistence(
        cast(async_sessionmaker[AsyncSession], cast(Any, factory)), FixedClock()
    )


def test_success_fresh_session_order_flush_commit_close_and_return_id() -> None:
    async def scenario() -> None:
        store = Store()
        factory = Factory(store)
        persistence = adapter(factory)
        value = candidate()
        result = await persistence.persist(value)
        assert result == build_incident_id(value)
        session = factory.sessions[0]
        assert session.entered and session.closed
        assert (
            session.transactions == 1
            and session.commits == 1
            and session.rollbacks == 0
        )
        assert session.flushes == 1 and session.pending_incident is not None
        assert [
            (row.finding_id, row.position) for row in session.pending_memberships
        ] == [(UUID(int=1), 0), (UUID(int=2), 1)]
        assert len(store.incidents) == 1 and len(store.memberships[result]) == 2
        await persistence.persist(value)
        assert len(factory.sessions) == 2 and factory.sessions[1].commits == 1
        assert len(store.incidents) == 1 and len(store.memberships[result]) == 2

    asyncio.run(scenario())


@pytest.mark.parametrize(
    "mutation", ["field", "missing", "extra", "position", "finding"]
)
def test_existing_state_conflicts_are_rejected(mutation: str) -> None:
    async def scenario() -> None:
        store = Store()
        persistence = adapter(Factory(store))
        value = candidate()
        incident_id = await persistence.persist(value)
        if mutation == "field":
            store.incidents[incident_id].service = "other"
        elif mutation == "missing":
            store.memberships[incident_id].pop()
        elif mutation == "extra":
            store.memberships[incident_id].append(store.memberships[incident_id][0])
        elif mutation == "position":
            store.memberships[incident_id][0].position = 9
        else:
            store.memberships[incident_id][0].finding_id = UUID(int=99)
        with pytest.raises(IncidentPersistenceConflictError):
            await persistence.persist(value)

    asyncio.run(scenario())


@pytest.mark.parametrize(
    "failure", [RuntimeError("incident failed"), asyncio.CancelledError()]
)
def test_incident_failure_or_cancellation_rolls_back_closes_and_propagates(
    failure: BaseException,
) -> None:
    async def scenario() -> None:
        factory = Factory(Store(), incident_failure=failure)
        with pytest.raises(type(failure)):
            await adapter(factory).persist(candidate())
        session = factory.sessions[0]
        assert session.closed and session.commits == 0 and session.rollbacks == 1
        assert not session.pending_memberships

    asyncio.run(scenario())


def test_second_membership_failure_is_safe_assignment_error_and_atomic() -> None:
    async def scenario() -> None:
        store = Store()
        factory = Factory(store, membership_failure_after=1)
        with pytest.raises(IncidentFindingAlreadyAssignedError):
            await adapter(factory).persist(candidate())
        session = factory.sessions[0]
        assert session.closed and session.commits == 0 and session.rollbacks == 1
        assert store.incidents == {} and store.memberships == {}
        assert len(session.pending_memberships) == 1

    asyncio.run(scenario())


def accepts_protocol(value: IncidentPersistence) -> IncidentPersistence:
    return value


def test_protocol_is_narrow_and_adapter_has_no_engine_disposal() -> None:
    persistence = adapter(Factory(Store()))
    assert accepts_protocol(persistence) is persistence
    public = {name for name in dir(IncidentPersistence) if not name.startswith("_")}
    assert public == {"persist"}
    assert not hasattr(persistence, "dispose") and not hasattr(persistence, "engine")
