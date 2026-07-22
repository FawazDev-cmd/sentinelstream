"""Background orchestration for queued log events."""

import logging

from app.application.contracts.event_processor import EventProcessor
from app.application.contracts.event_queue import EventQueue

logger = logging.getLogger(__name__)


class EventWorker:
    def __init__(self, queue: EventQueue, processor: EventProcessor) -> None:
        self._queue = queue
        self._processor = processor

    async def run(self) -> None:
        while True:
            event = await self._queue.consume()
            try:
                await self._processor.process(event)
            except Exception as error:
                logger.error(
                    "event processing failed event_id=%s service=%s environment=%s "
                    "level=%s error_type=%s",
                    event.event_id,
                    event.service,
                    event.environment,
                    event.level.value,
                    type(error).__name__,
                )
            finally:
                self._queue.task_done()
