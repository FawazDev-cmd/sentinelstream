"""Tests for deterministic incident generation orchestration."""

import asyncio
from dataclasses import FrozenInstanceError
from datetime import UTC, datetime, timedelta, timezone
from typing import Any
from uuid import UUID

import pytest

from app.application.incidents import (
    DeterministicIncidentGrouper,
    IncidentGroupingPolicy,
)
from app.application.incidents.generation import (
    DuplicateEligibleIncidentFindingError,
    EligibleIncidentFinding,
    EligibleIncidentFindingCursor,
    EligibleIncidentFindingPage,
    GenerateIncidents,
    IncidentGenerationCursorProgressError,
    IncidentGenerationRequest,
    IncidentGenerationResult,
)
from app.application.queries.anomalies import PersistedAnomalyFinding
from app.domain.anomalies import AnomalySeverity, AnomalyType
from app.domain.incidents import IncidentCandidate

BASE = datetime(2026, 7, 22, 12, tzinfo=UTC)


def eligible(
    index: int, minute: int, service: str = "payments"
) -> EligibleIncidentFinding:
    finding = PersistedAnomalyFinding(
        UUID(int=index),
        UUID(int=100 + index),
        AnomalyType.HIGH_LATENCY,
        AnomalySeverity.HIGH,
        f"rule.{index}",
        "Latency",
        ("safe",),
        BASE + timedelta(seconds=index),
    )
    return EligibleIncidentFinding(
        finding, service, "prod", BASE + timedelta(minutes=minute)
    )


class Reader:
    def __init__(self, pages: list[EligibleIncidentFindingPage]) -> None:
        self.pages = pages
        self.calls: list[dict[str, Any]] = []

    async def read_batch(self, **values):  # type: ignore[no-untyped-def]
        self.calls.append(values)
        return self.pages.pop(0)


class Persistence:
    def __init__(self, fail_at: int | None = None) -> None:
        self.candidates: list[IncidentCandidate] = []
        self.fail_at = fail_at

    async def persist(self, candidate: IncidentCandidate) -> UUID:
        if self.fail_at is not None and len(self.candidates) == self.fail_at:
            raise RuntimeError("failed")
        self.candidates.append(candidate)
        return UUID(int=1000 + len(self.candidates))


def pages() -> list[EligibleIncidentFindingPage]:
    first = (eligible(1, 0), eligible(2, 4))
    second = (eligible(3, 8), eligible(4, 20, "catalog"), eligible(5, 24, "catalog"))
    cursor = EligibleIncidentFindingCursor(
        first[-1].event_timestamp, first[-1].finding.created_at, first[-1].finding.id
    )
    return [
        EligibleIncidentFindingPage(first, cursor),
        EligibleIncidentFindingPage(second),
    ]


def test_request_values_cursor_page_and_result_validation() -> None:
    offset = timezone(timedelta(hours=2))
    request = IncidentGenerationRequest(
        BASE.astimezone(offset), BASE.astimezone(offset)
    )
    assert request.event_time_from == BASE and request.batch_size == 500
    for kwargs in (
        {"event_time_from": BASE.replace(tzinfo=None), "event_time_to": BASE},
        {"event_time_from": BASE, "event_time_to": BASE - timedelta(seconds=1)},
        {"event_time_from": BASE, "event_time_to": BASE, "batch_size": 1},
        {"event_time_from": BASE, "event_time_to": BASE, "batch_size": 10001},
    ):
        with pytest.raises(ValueError):
            IncidentGenerationRequest(**kwargs)
    assert IncidentGenerationRequest(BASE, BASE, batch_size=2).batch_size == 2
    assert IncidentGenerationRequest(BASE, BASE, batch_size=10000).batch_size == 10000
    value = eligible(1, 0)
    assert (
        value.to_grouping_input().finding is value.finding
        and not hasattr(value, "message")
        and not hasattr(value, "metadata")
    )
    with pytest.raises(ValueError):
        EligibleIncidentFinding(value.finding, " ", "prod", BASE)
    with pytest.raises(FrozenInstanceError):
        value.service = "x"  # type: ignore[misc]
    assert IncidentGenerationResult(0, 0, 0, (), 1).incident_ids == ()
    with pytest.raises(ValueError):
        IncidentGenerationResult(0, 1, 0, ())


def test_multi_page_full_window_grouping_and_order() -> None:
    async def scenario() -> None:
        reader = Reader(pages())
        persistence = Persistence()
        policy = IncidentGroupingPolicy()
        result = await GenerateIncidents(
            reader, DeterministicIncidentGrouper(policy), persistence, policy
        ).execute(IncidentGenerationRequest(BASE, BASE + timedelta(hours=1), 2))
        assert result == IncidentGenerationResult(
            5, 2, 2, (UUID(int=1001), UUID(int=1002)), 2
        )
        assert [candidate.finding_ids for candidate in persistence.candidates] == [
            (UUID(int=1), UUID(int=2), UUID(int=3)),
            (UUID(int=4), UUID(int=5)),
        ]
        assert len(reader.calls) == 2 and reader.calls[1]["after"] is not None

    asyncio.run(scenario())


def test_duplicate_and_nonadvancing_cursor_are_rejected_before_grouping() -> None:
    async def scenario() -> None:
        item = eligible(1, 0)
        cursor = EligibleIncidentFindingCursor(
            item.event_timestamp, item.finding.created_at, item.finding.id
        )
        duplicate = Reader(
            [
                EligibleIncidentFindingPage((item,), cursor),
                EligibleIncidentFindingPage((item,)),
            ]
        )
        with pytest.raises(DuplicateEligibleIncidentFindingError):
            await GenerateIncidents(
                duplicate,
                DeterministicIncidentGrouper(IncidentGroupingPolicy()),
                Persistence(),
                IncidentGroupingPolicy(),
            ).execute(IncidentGenerationRequest(BASE, BASE))
        repeated = Reader(
            [
                EligibleIncidentFindingPage((item,), cursor),
                EligibleIncidentFindingPage((), cursor),
            ]
        )
        with pytest.raises(IncidentGenerationCursorProgressError):
            await GenerateIncidents(
                repeated,
                DeterministicIncidentGrouper(IncidentGroupingPolicy()),
                Persistence(),
                IncidentGroupingPolicy(),
            ).execute(IncidentGenerationRequest(BASE, BASE))

    asyncio.run(scenario())


def test_empty_undersized_and_fail_fast_persistence() -> None:
    async def scenario() -> None:
        policy = IncidentGroupingPolicy()
        empty_persistence = Persistence()
        empty = await GenerateIncidents(
            Reader([EligibleIncidentFindingPage(())]),
            DeterministicIncidentGrouper(policy),
            empty_persistence,
            policy,
        ).execute(IncidentGenerationRequest(BASE, BASE))
        assert (
            empty == IncidentGenerationResult(0, 0, 0, (), 1)
            and not empty_persistence.candidates
        )
        failure = Persistence(fail_at=1)
        with pytest.raises(RuntimeError):
            await GenerateIncidents(
                Reader(pages()), DeterministicIncidentGrouper(policy), failure, policy
            ).execute(IncidentGenerationRequest(BASE, BASE + timedelta(hours=1), 2))
        assert len(failure.candidates) == 1

    asyncio.run(scenario())
