"""FastAPI application construction and worker lifecycle."""

import asyncio
import logging
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager, suppress
from uuid import UUID

from fastapi import FastAPI

from app.application.contracts.clock import Clock, SystemClock
from app.application.contracts.event_processor import EventProcessor
from app.application.contracts.event_queue import EventQueue
from app.application.services.ingestion import IngestionService
from app.application.services.processor import LoggingEventProcessor
from app.application.services.worker import EventWorker
from app.infrastructure.queue.memory import InMemoryEventQueue
from app.monitoring.logging import configure_logging
from app.presentation.api.routes.health import router as health_router
from app.presentation.api.routes.logs import router as logs_router
from app.shared.config import Settings, get_settings

logger = logging.getLogger(__name__)


def create_app(
    settings: Settings | None = None,
    event_queue: EventQueue | None = None,
    event_processor: EventProcessor | None = None,
    clock: Clock | None = None,
    event_id_factory: Callable[[], UUID] | None = None,
) -> FastAPI:
    """Build one application with one queue and one lifespan-managed worker."""
    active_settings = settings or get_settings()
    configure_logging(active_settings)
    queue = event_queue or InMemoryEventQueue(active_settings.event_queue_max_size)
    processor = event_processor or LoggingEventProcessor()
    ingestion_service = IngestionService(
        clock or SystemClock(),
        queue,
        **({"id_generator": event_id_factory} if event_id_factory is not None else {}),
    )
    worker = EventWorker(queue, processor)

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        worker_task = asyncio.create_task(
            worker.run(), name="sentinelstream-event-worker"
        )
        application.state.worker_task = worker_task
        logger.info("event worker started")
        try:
            yield
        finally:
            try:
                async with asyncio.timeout(
                    active_settings.worker_shutdown_timeout_seconds
                ):
                    await queue.join()
            except TimeoutError:
                logger.warning("event queue did not drain within shutdown timeout")
            worker_task.cancel()
            with suppress(asyncio.CancelledError):
                await worker_task
            logger.info("event worker stopped")

    application = FastAPI(
        title=active_settings.application_name,
        version=active_settings.application_version,
        lifespan=lifespan,
    )
    application.state.settings = active_settings
    application.state.ingestion_service = ingestion_service
    application.include_router(health_router)
    application.include_router(logs_router)
    return application


app = create_app()
