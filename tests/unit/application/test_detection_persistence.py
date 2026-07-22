"""Tests for detection-aware processing orchestration."""

import asyncio
from collections.abc import Sequence
from uuid import uuid4

import pytest

from app.application.exceptions import DetectionResultEventMismatchError
from app.application.services.persistence import DetectAndPersistLogEventProcessor
from app.domain.anomalies import (
    AnomalyFinding,
    AnomalySeverity,
    AnomalyType,
    DetectionResult,
)
from app.domain.logs import LogEvent
from tests.unit.infrastructure.test_models import complete_event


class RecordingDetector:
    def __init__(
        self,
        result: DetectionResult | None = None,
        failure: BaseException | None = None,
    ) -> None:
        self.result = result
        self.failure = failure
        self.events: list[LogEvent] = []

    def detect(self, event: LogEvent) -> DetectionResult:
        self.events.append(event)
        if self.failure is not None:
            raise self.failure
        assert self.result is not None
        return self.result


class RecordingPersistence:
    def __init__(self, failure: BaseException | None = None) -> None:
        self.calls: list[tuple[LogEvent, tuple[AnomalyFinding, ...]]] = []
        self.failure = failure

    async def persist(
        self, event: LogEvent, findings: Sequence[AnomalyFinding]
    ) -> None:
        self.calls.append((event, tuple(findings)))
        if self.failure is not None:
            raise self.failure


def finding(rule_id: str = "rule.v1") -> AnomalyFinding:
    return AnomalyFinding(
        AnomalyType.ERROR_LEVEL,
        AnomalySeverity.HIGH,
        rule_id,
        "Finding",
        ("level=error",),
    )


def test_processor_detects_and_persists_once_without_mutation() -> None:
    event = complete_event()
    before = event.to_dict()
    findings = (finding("one"), finding("two"))
    detector = RecordingDetector(DetectionResult(event.event_id, findings))
    persistence = RecordingPersistence()
    asyncio.run(DetectAndPersistLogEventProcessor(detector, persistence).process(event))
    assert detector.events == [event]
    assert persistence.calls == [(event, findings)]
    assert persistence.calls[0][0] is event
    assert event.to_dict() == before


def test_zero_findings_are_still_persisted_with_event() -> None:
    event = complete_event()
    persistence = RecordingPersistence()
    processor = DetectAndPersistLogEventProcessor(
        RecordingDetector(DetectionResult(event.event_id, ())), persistence
    )
    asyncio.run(processor.process(event))
    assert persistence.calls == [(event, ())]


def test_mismatched_result_is_rejected_before_persistence() -> None:
    event = complete_event()
    persistence = RecordingPersistence()
    processor = DetectAndPersistLogEventProcessor(
        RecordingDetector(DetectionResult(uuid4(), (finding(),))), persistence
    )
    with pytest.raises(DetectionResultEventMismatchError):
        asyncio.run(processor.process(event))
    assert persistence.calls == []


@pytest.mark.parametrize("stage", ["detector", "persistence"])
def test_failures_propagate_without_suppression(stage: str) -> None:
    event = complete_event()
    failure = RuntimeError(f"{stage} failure")
    detector = RecordingDetector(
        DetectionResult(event.event_id, ()), failure if stage == "detector" else None
    )
    persistence = RecordingPersistence(failure if stage == "persistence" else None)
    with pytest.raises(RuntimeError, match=f"{stage} failure"):
        asyncio.run(
            DetectAndPersistLogEventProcessor(detector, persistence).process(event)
        )
    assert len(detector.events) == 1
    assert len(persistence.calls) == (0 if stage == "detector" else 1)


@pytest.mark.parametrize("stage", ["detector", "persistence"])
def test_cancellation_propagates(stage: str) -> None:
    event = complete_event()
    failure = asyncio.CancelledError()
    detector = RecordingDetector(
        DetectionResult(event.event_id, ()), failure if stage == "detector" else None
    )
    persistence = RecordingPersistence(failure if stage == "persistence" else None)
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(
            DetectAndPersistLogEventProcessor(detector, persistence).process(event)
        )
