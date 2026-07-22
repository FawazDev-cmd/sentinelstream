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
        logger.info("worker_started", extra={"lifecycle_event": "worker_started"})
        try:
            while True:
                event = await self._queue.consume()
                try:
                    await self._processor.process(event)
                except Exception as error:
                    logger.error(
                        "worker_processing_failed",
                        extra={
                            "lifecycle_event": "processing_failed",
                            "processing_id": str(event.event_id),
                            "service": event.service,
                            "environment": event.environment,
                            "failure_stage": "worker_processor",
                            "exception_type": type(error).__name__,
                            "safe_error_message": "event processor failed",
                            "outcome": "failure",
                        },
                    )
                finally:
                    self._queue.task_done()
        finally:
            logger.info("worker_stopping", extra={"lifecycle_event": "worker_stopping"})
            logger.info("worker_stopped", extra={"lifecycle_event": "worker_stopped"})
