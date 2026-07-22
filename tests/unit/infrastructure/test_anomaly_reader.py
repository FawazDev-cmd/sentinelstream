"""Tests for anomaly reverse mapping and SQLAlchemy reader."""

import asyncio
from datetime import UTC, datetime
from typing import Any, cast
from uuid import UUID

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.sql import Select

from app.application.queries.anomalies import AnomalyFindingCursor, AnomalyFindingQuery
from app.domain.anomalies import AnomalySeverity, AnomalyType
from app.infrastructure.database.anomaly_reader import SqlAlchemyAnomalyFindingReader
from app.infrastructure.database.mapper import map_anomaly_finding_record
from app.infrastructure.database.models import AnomalyFindingRecord

MOMENT = datetime(2026, 7, 22, 12, tzinfo=UTC)


def record(number: int, *, moment: datetime = MOMENT) -> AnomalyFindingRecord:
    return AnomalyFindingRecord(
        id=UUID(int=number),
        event_id=UUID(int=100 + number),
        anomaly_type="high_latency",
        severity="critical",
        rule_id=f"rule.{number}.v1",
        title="High request latency",
        evidence=["latency_ms=6000"],
        created_at=moment,
    )


def test_reverse_mapping_copies_evidence_reconstructs_enums_and_validates() -> None:
    source = record(1)
    mapped = map_anomaly_finding_record(source)
    assert mapped.id == source.id and mapped.event_id == source.event_id
    assert mapped.anomaly_type is AnomalyType.HIGH_LATENCY
    assert mapped.severity is AnomalySeverity.CRITICAL
    assert mapped.evidence == ("latency_ms=6000",)
    source.evidence.append("changed")
    assert mapped.evidence == ("latency_ms=6000",)
    source.anomaly_type = "invalid"
    with pytest.raises(ValueError):
        map_anomaly_finding_record(source)
    source.anomaly_type, source.severity = "high_latency", "invalid"
    with pytest.raises(ValueError):
        map_anomaly_finding_record(source)
    source.severity, source.created_at = "critical", datetime(2026, 1, 1)
    with pytest.raises(ValueError, match="timezone-aware"):
        map_anomaly_finding_record(source)
    source.created_at, source.evidence = MOMENT, [1]  # type: ignore[list-item]
    with pytest.raises(ValueError, match="evidence"):
        map_anomaly_finding_record(source)


class Result:
    def __init__(self, rows: list[AnomalyFindingRecord]) -> None:
        self.rows = rows

    def all(self) -> list[AnomalyFindingRecord]:
        return self.rows


class FakeSession:
    def __init__(
        self, rows: list[AnomalyFindingRecord], failure: BaseException | None = None
    ) -> None:
        self.rows, self.failure = rows, failure
        self.statement: Select[Any] | None = None
        self.entered = self.exited = False

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
        self, rows: list[AnomalyFindingRecord], failure: BaseException | None = None
    ) -> None:
        self.rows, self.failure = rows, failure
        self.sessions: list[FakeSession] = []

    def __call__(self) -> FakeSession:
        session = FakeSession(self.rows, self.failure)
        self.sessions.append(session)
        return session


def reader(factory: Factory) -> SqlAlchemyAnomalyFindingReader:
    return SqlAlchemyAnomalyFindingReader(
        cast(async_sessionmaker[AsyncSession], cast(Any, factory))
    )


def test_reader_fresh_sessions_no_commit_and_complete_sql_shape() -> None:
    async def scenario() -> None:
        factory = Factory([])
        query = AnomalyFindingQuery(
            event_id=UUID(int=2),
            anomaly_type=AnomalyType.HIGH_LATENCY,
            severity=AnomalySeverity.CRITICAL,
            rule_id="rule.v1",
            start_time=MOMENT,
            end_time=MOMENT,
            limit=10,
            cursor=AnomalyFindingCursor(MOMENT, UUID(int=9)),
        )
        adapter = reader(factory)
        await adapter.list(query)
        await adapter.list(AnomalyFindingQuery())
        assert len(factory.sessions) == 2 and all(
            s.entered and s.exited for s in factory.sessions
        )
        assert all(not hasattr(s, "commit") for s in factory.sessions)
        statement = factory.sessions[0].statement
        assert statement is not None
        sql = str(statement)
        for fragment in (
            "anomaly_findings.event_id =",
            "anomaly_findings.anomaly_type =",
            "anomaly_findings.severity =",
            "anomaly_findings.rule_id =",
            "anomaly_findings.created_at >=",
            "anomaly_findings.created_at <=",
            "anomaly_findings.created_at <",
            "anomaly_findings.id <",
            " OR ",
            "ORDER BY anomaly_findings.created_at DESC, anomaly_findings.id DESC",
        ):
            assert fragment in sql
        assert (
            statement._limit_clause is not None and statement._limit_clause.value == 11
        )

    asyncio.run(scenario())


def test_reader_lookahead_cursor_and_final_page() -> None:
    page = asyncio.run(
        reader(Factory([record(3), record(2), record(1)])).list(
            AnomalyFindingQuery(limit=2)
        )
    )
    assert [item.id.int for item in page.items] == [3, 2]
    assert page.next_cursor == AnomalyFindingCursor(MOMENT, UUID(int=2))
    final = asyncio.run(reader(Factory([record(1)])).list(AnomalyFindingQuery(limit=2)))
    assert len(final.items) == 1 and final.next_cursor is None


@pytest.mark.parametrize(
    "failure", [RuntimeError("database failed"), asyncio.CancelledError()]
)
def test_reader_failure_and_cancellation_propagate_and_close(
    failure: BaseException,
) -> None:
    factory = Factory([], failure)
    with pytest.raises(type(failure)):
        asyncio.run(reader(factory).list(AnomalyFindingQuery()))
    assert factory.sessions[0].exited
    assert not hasattr(reader(factory), "dispose")
