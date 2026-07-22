import asyncio
import logging

import pytest

from app.application.services.persistence import PersistenceEventProcessor
from app.domain.logs import LogEvent
from tests.unit.infrastructure.test_models import complete_event


class RecordingRepository:
    def __init__(self, failure: Exception | None = None) -> None:
        self.events: list[LogEvent] = []
        self.failure = failure

    async def add(self, event: LogEvent) -> None:
        self.events.append(event)
        if self.failure is not None:
            raise self.failure


def test_processor_delegates_exact_event_once_without_mutation(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG)
    repository = RecordingRepository()
    processor = PersistenceEventProcessor(repository)
    event = complete_event()
    before = event.to_dict()
    asyncio.run(processor.process(event))
    assert repository.events == [event] and repository.events[0] is event
    assert event.to_dict() == before
    assert "failed" not in caplog.text
    assert "metadata" not in caplog.text
    assert "details" not in caplog.text
    assert f"event_id={event.event_id}" in caplog.text


def test_repository_failure_propagates_without_retry() -> None:
    repository = RecordingRepository(RuntimeError("failure"))
    processor = PersistenceEventProcessor(repository)
    event = complete_event()
    with pytest.raises(RuntimeError, match="failure"):
        asyncio.run(processor.process(event))
    assert repository.events == [event]


def test_worker_continues_after_persistence_failure_and_completes_queue(
    caplog: pytest.LogCaptureFixture,
) -> None:
    from contextlib import suppress

    from app.application.services.worker import EventWorker
    from app.infrastructure.queue.memory import InMemoryEventQueue

    class FailsFirstRepository:
        def __init__(self) -> None:
            self.events: list[LogEvent] = []

        async def add(self, event: LogEvent) -> None:
            self.events.append(event)
            if len(self.events) == 1:
                raise RuntimeError("database secret")

    async def scenario() -> None:
        repository = FailsFirstRepository()
        queue = InMemoryEventQueue(2)
        task = asyncio.create_task(
            EventWorker(queue, PersistenceEventProcessor(repository)).run()
        )
        first = complete_event()
        second = LogEvent(
            event_id=UUID(int=2),
            timestamp=first.timestamp,
            received_at=first.received_at,
            service="later",
            environment="test",
            level=first.level,
            message="later secret",
            metadata={"secret": "value"},
        )
        await queue.publish(first)
        await queue.publish(second)
        await asyncio.wait_for(queue.join(), 0.2)
        assert repository.events == [first, second]
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task

    from uuid import UUID

    asyncio.run(scenario())
    assert "database secret" not in caplog.text
    assert "later secret" not in caplog.text
    assert "metadata" not in caplog.text
