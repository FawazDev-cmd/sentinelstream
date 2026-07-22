import asyncio
from datetime import UTC, datetime
from uuid import UUID

import pytest

from app.application.exceptions import EventQueueFullError
from app.domain.logs import LogEvent, LogLevel
from app.infrastructure.queue.memory import InMemoryEventQueue


def event(number: int = 1) -> LogEvent:
    return LogEvent(
        event_id=UUID(int=number),
        timestamp=datetime(2026, 7, 22, tzinfo=UTC),
        received_at=datetime(2026, 7, 22, tzinfo=UTC),
        service="api",
        environment="test",
        level=LogLevel.INFO,
        message="secret message",
        exception_message="secret exception",
        metadata={"secret": "metadata"},
    )


def test_queue_round_trip_and_join() -> None:
    async def scenario() -> None:
        queue = InMemoryEventQueue(1)
        expected = event()
        await queue.publish(expected)
        assert await queue.consume() is expected
        queue.task_done()
        await asyncio.wait_for(queue.join(), 0.1)

    asyncio.run(scenario())


@pytest.mark.parametrize("size", [0, -1])
def test_invalid_maximum_size(size: int) -> None:
    with pytest.raises(ValueError):
        InMemoryEventQueue(size)


def test_maximum_size_and_failed_publish_preserve_existing_event() -> None:
    async def scenario() -> None:
        queue = InMemoryEventQueue(1)
        first = event(1)
        await queue.publish(first)
        with pytest.raises(EventQueueFullError):
            await queue.publish(event(2))
        assert await queue.consume() is first
        queue.task_done()
        await queue.join()

    asyncio.run(scenario())


def test_join_waits_while_item_is_unfinished() -> None:
    async def scenario() -> None:
        queue = InMemoryEventQueue(1)
        await queue.publish(event())
        await queue.consume()
        joined = asyncio.create_task(queue.join())
        await asyncio.sleep(0)
        assert not joined.done()
        queue.task_done()
        await asyncio.wait_for(joined, 0.1)

    asyncio.run(scenario())
