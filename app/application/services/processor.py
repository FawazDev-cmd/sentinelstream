"""Safe default event processor for the Day 4 worker."""

import logging

from app.domain.logs import LogEvent

logger = logging.getLogger(__name__)


class LoggingEventProcessor:
    async def process(self, event: LogEvent) -> None:
        logger.debug(
            "log event processed event_id=%s service=%s environment=%s level=%s",
            event.event_id,
            event.service,
            event.environment,
            event.level.value,
        )
