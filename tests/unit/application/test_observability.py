"""Structured processing and worker observability tests."""

import asyncio
import json
import logging
from contextlib import suppress
from typing import cast

import pytest

from app.application.incidents import GenerateIncidents
from app.application.services.persistence import DetectAndPersistLogEventProcessor
from app.application.services.worker import EventWorker
from app.domain.anomalies import DetectionResult
from app.infrastructure.queue.memory import InMemoryEventQueue
from app.monitoring.logging import JsonFormatter
from tests.unit.application.test_detection_persistence import (
    RecordingDetector,
    RecordingPersistence,
    finding,
)
from tests.unit.application.test_queue import event as queued_event
from tests.unit.application.test_runtime_incident_generation import RecordingGenerator
from tests.unit.infrastructure.test_models import complete_event


def log_field(record: logging.LogRecord, name: str) -> object:
    return record.__dict__[name]


def lifecycle_records(caplog: pytest.LogCaptureFixture) -> list[logging.LogRecord]:
    return [record for record in caplog.records if hasattr(record, "lifecycle_event")]


def test_success_lifecycle_order_correlation_summary_and_monotonic_duration(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.INFO)
    value = complete_event()
    ticks = iter((100.0, 100.125))
    generator = RecordingGenerator([])
    processor = DetectAndPersistLogEventProcessor(
        RecordingDetector(DetectionResult(value.event_id, (finding(),))),
        RecordingPersistence(),
        cast(GenerateIncidents, generator),
        monotonic_clock=lambda: next(ticks),
    )
    asyncio.run(processor.process(value))
    records = lifecycle_records(caplog)
    assert [log_field(record, "lifecycle_event") for record in records] == [
        "processing_started",
        "anomaly_detection_completed",
        "log_persisted",
        "anomaly_persisted",
        "incident_generation_started",
        "incident_generation_completed",
        "processing_completed",
    ]
    assert {log_field(record, "processing_id") for record in records} == {
        str(value.event_id)
    }
    summary = records[-1]
    assert log_field(summary, "logs_processed") == 1
    assert log_field(summary, "anomalies_detected") == 1
    assert log_field(summary, "incidents_generated") == 0
    assert log_field(summary, "processing_duration_ms") == 125.0
    assert cast(float, log_field(summary, "total_processing_duration_ms")) >= 0
    assert log_field(summary, "outcome") == "success"
    assert (
        log_field(summary, "service") == value.service
        and log_field(summary, "environment") == value.environment
    )


def test_failure_is_safe_classified_timed_and_still_propagates(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.INFO)
    value = complete_event()
    ticks = iter((4.0, 4.01))
    secret = "database-url=postgresql://secret raw-message-secret"
    generator = RecordingGenerator([], RuntimeError(secret))
    processor = DetectAndPersistLogEventProcessor(
        RecordingDetector(DetectionResult(value.event_id, (finding(),))),
        RecordingPersistence(),
        cast(GenerateIncidents, generator),
        monotonic_clock=lambda: next(ticks),
    )
    with pytest.raises(RuntimeError, match="database-url"):
        asyncio.run(processor.process(value))
    failure = lifecycle_records(caplog)[-1]
    assert log_field(failure, "lifecycle_event") == "processing_failed"
    assert log_field(failure, "failure_stage") == "incident_generation"
    assert log_field(failure, "exception_type") == "RuntimeError"
    assert log_field(failure, "safe_error_message") == "processing stage failed"
    assert cast(float, log_field(failure, "processing_duration_ms")) >= 0
    assert secret not in caplog.text
    assert len(generator.requests) == 1


def test_json_formatter_emits_safe_structured_fields_only() -> None:
    record = logging.LogRecord(
        "test", logging.INFO, __file__, 1, "processing_completed", (), None
    )
    record.__dict__.update(
        {
            "processing_id": "stable-id",
            "lifecycle_event": "processing_completed",
            "logs_processed": 1,
            "processing_duration_ms": 2.5,
            "raw_payload": {"secret": "do-not-log"},
        }
    )
    payload = json.loads(JsonFormatter().format(record))
    assert payload["processing_id"] == "stable-id"
    assert payload["logs_processed"] == 1
    assert payload["processing_duration_ms"] == 2.5
    assert "raw_payload" not in payload and "do-not-log" not in str(payload)


def test_worker_lifecycle_events_are_emitted_without_behavior_change(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.INFO)

    class Processor:
        async def process(self, value: object) -> None:
            pass

    async def scenario() -> None:
        queue = InMemoryEventQueue(1)
        task = asyncio.create_task(EventWorker(queue, Processor()).run())
        await queue.publish(queued_event())
        await asyncio.wait_for(queue.join(), 0.2)
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task

    asyncio.run(scenario())
    events = [
        log_field(record, "lifecycle_event") for record in lifecycle_records(caplog)
    ]
    assert events == ["worker_started", "worker_stopping", "worker_stopped"]
