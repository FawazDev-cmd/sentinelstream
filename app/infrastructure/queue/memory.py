"""Bounded in-process event queue."""

import asyncio

from app.application.exceptions import EventQueueFullError
from app.domain.logs import LogEvent


class InMemoryEventQueue:
    def __init__(self, max_size: int) -> None:
        if isinstance(max_size, bool) or not isinstance(max_size, int):
            raise TypeError("event queue maximum size must be an integer")
        if max_size < 1:
            raise ValueError("event queue maximum size must be greater than zero")
        self._queue: asyncio.Queue[LogEvent] = asyncio.Queue(maxsize=max_size)

    async def publish(self, event: LogEvent) -> None:
        try:
            self._queue.put_nowait(event)
        except asyncio.QueueFull as error:
            raise EventQueueFullError from error

    async def consume(self) -> LogEvent:
        return await self._queue.get()

    def task_done(self) -> None:
        self._queue.task_done()

    async def join(self) -> None:
        await self._queue.join()
