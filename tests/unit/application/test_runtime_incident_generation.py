"""Day 15 post-persistence incident-generation orchestration tests."""

import asyncio
from collections.abc import Sequence
from datetime import timedelta
from typing import cast

import pytest

from app.application.incidents import GenerateIncidents, IncidentGenerationRequest
from app.application.services.persistence import DetectAndPersistLogEventProcessor
from app.domain.anomalies import AnomalyFinding, DetectionResult
from app.domain.logs import LogEvent
from tests.unit.application.test_detection_persistence import (
    RecordingDetector,
    RecordingPersistence,
    finding,
)
from tests.unit.infrastructure.test_models import complete_event


class RecordingGenerator:
    def __init__(self, order: list[str], failure: BaseException | None = None) -> None:
        self.order = order
        self.failure = failure
        self.requests: list[IncidentGenerationRequest] = []

    async def execute(self, request: IncidentGenerationRequest) -> object:
        self.order.append("generation")
        self.requests.append(request)
        if self.failure is not None:
            raise self.failure
        return object()


class OrderedPersistence(RecordingPersistence):
    def __init__(self, order: list[str]) -> None:
        super().__init__()
        self.order = order

    async def persist(
        self, event: LogEvent, findings: Sequence[AnomalyFinding]
    ) -> None:
        await super().persist(event, findings)
        self.order.append("persistence")


def test_generation_runs_once_after_persistence_with_rolling_event_window() -> None:
    event = complete_event()
    order: list[str] = []
    generator = RecordingGenerator(order)
    processor = DetectAndPersistLogEventProcessor(
        RecordingDetector(DetectionResult(event.event_id, (finding(),))),
        OrderedPersistence(order),
        cast(GenerateIncidents, generator),
    )
    asyncio.run(processor.process(event))
    assert order == ["persistence", "generation"]
    assert generator.requests == [
        IncidentGenerationRequest(event.timestamp - timedelta(hours=1), event.timestamp)
    ]


def test_empty_findings_skip_generation() -> None:
    event = complete_event()
    generator = RecordingGenerator([])
    asyncio.run(
        DetectAndPersistLogEventProcessor(
            RecordingDetector(DetectionResult(event.event_id, ())),
            RecordingPersistence(),
            cast(GenerateIncidents, generator),
        ).process(event)
    )
    assert generator.requests == []


def test_generation_failure_propagates_without_retry() -> None:
    event = complete_event()
    generator = RecordingGenerator([], RuntimeError("generation failed"))
    processor = DetectAndPersistLogEventProcessor(
        RecordingDetector(DetectionResult(event.event_id, (finding(),))),
        RecordingPersistence(),
        cast(GenerateIncidents, generator),
    )
    with pytest.raises(RuntimeError, match="generation failed"):
        asyncio.run(processor.process(event))
    assert len(generator.requests) == 1


@pytest.mark.parametrize(
    "lookback", [timedelta(seconds=1), timedelta(minutes=17), timedelta(days=1)]
)
def test_configured_lookback_deterministically_controls_lower_bound(
    lookback: timedelta,
) -> None:
    event = complete_event()
    generator = RecordingGenerator([])
    processor = DetectAndPersistLogEventProcessor(
        RecordingDetector(DetectionResult(event.event_id, (finding(),))),
        RecordingPersistence(),
        cast(GenerateIncidents, generator),
        lookback,
    )
    asyncio.run(processor.process(event))
    assert generator.requests == [
        IncidentGenerationRequest(event.timestamp - lookback, event.timestamp)
    ]
