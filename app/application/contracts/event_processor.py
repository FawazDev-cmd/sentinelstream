"""Contract for processing one trusted event."""

from typing import Protocol

from app.domain.logs import LogEvent


class EventProcessor(Protocol):
    async def process(self, event: LogEvent) -> None: ...
