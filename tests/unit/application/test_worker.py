import asyncio
import logging
from collections.abc import Sequence
from contextlib import suppress

import pytest

from app.application.services.processor import LoggingEventProcessor
from app.application.services.worker import EventWorker
from app.domain.logs import LogEvent
from app.infrastructure.queue.memory import InMemoryEventQueue
from tests.unit.application.test_queue import event


class RecordingProcessor:
    def __init__(self, fail_ids: Sequence[int] = ()) -> None:
        self.events: list[LogEvent] = []
        self.fail_ids = fail_ids

    async def process(self, item: LogEvent) -> None:
        self.events.append(item)
        if item.event_id.int in self.fail_ids:
            raise RuntimeError("processor secret")


def test_worker_processes_multiple_events_in_order_and_completes_tasks() -> None:
    async def scenario() -> None:
        queue = InMemoryEventQueue(3)
        processor = RecordingProcessor()
        worker = EventWorker(queue, processor)
        task = asyncio.create_task(worker.run())
        for number in (1, 2, 3):
            await queue.publish(event(number))
        await asyncio.wait_for(queue.join(), 0.2)
        assert [item.event_id.int for item in processor.events] == [1, 2, 3]
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task
        assert task.cancelled()

    asyncio.run(scenario())


def test_processor_failure_is_completed_and_later_event_is_processed(
    caplog: pytest.LogCaptureFixture,
) -> None:
    async def scenario() -> None:
        queue = InMemoryEventQueue(2)
        processor = RecordingProcessor((1,))
        task = asyncio.create_task(EventWorker(queue, processor).run())
        await queue.publish(event(1))
        await queue.publish(event(2))
        await asyncio.wait_for(queue.join(), 0.2)
        assert [item.event_id.int for item in processor.events] == [1, 2]
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task

    asyncio.run(scenario())


def test_cancellation_is_clean_and_not_logged_as_failure(
    caplog: pytest.LogCaptureFixture,
) -> None:
    async def scenario() -> None:
        queue = InMemoryEventQueue(1)
        task = asyncio.create_task(EventWorker(queue, RecordingProcessor()).run())
        await asyncio.sleep(0)
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task
        assert task.cancelled()

    asyncio.run(scenario())
    assert "event processing failed" not in caplog.text


def test_default_processor_logging_excludes_sensitive_fields(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG)
    asyncio.run(LoggingEventProcessor().process(event()))
    output = caplog.text
    assert "secret message" not in output
    assert "secret exception" not in output
    assert "metadata" not in output
    assert "service=api" in output
