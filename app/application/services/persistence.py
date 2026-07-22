"""Persist trusted events through the repository boundary."""

import logging

from app.application.contracts.repository import LogEventRepository
from app.domain.logs import LogEvent

logger = logging.getLogger(__name__)


class PersistenceEventProcessor:
    def __init__(self, repository: LogEventRepository) -> None:
        self._repository = repository

    async def process(self, event: LogEvent) -> None:
        await self._repository.add(event)
        logger.debug(
            "log event persisted event_id=%s service=%s environment=%s level=%s",
            event.event_id,
            event.service,
            event.environment,
            event.level.value,
        )
