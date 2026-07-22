"""Persistence boundary for trusted log events."""

from typing import Protocol

from app.domain.logs import LogEvent


class LogEventRepository(Protocol):
    async def add(self, event: LogEvent) -> None: ...
