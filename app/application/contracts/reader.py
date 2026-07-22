"""Read-side contract for persisted log events."""

from typing import Protocol

from app.application.queries.logs import LogEventPage, LogEventQuery


class LogEventReader(Protocol):
    async def list(self, query: LogEventQuery) -> LogEventPage: ...
