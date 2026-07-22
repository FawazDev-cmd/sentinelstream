"""FastAPI application construction and runtime lifecycle."""

import asyncio
import logging
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager, suppress
from uuid import UUID

from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncEngine

from app.application.contracts.clock import Clock, SystemClock
from app.application.contracts.event_processor import EventProcessor
from app.application.contracts.event_queue import EventQueue
from app.application.contracts.reader import LogEventReader
from app.application.services.ingestion import IngestionService
from app.application.services.persistence import PersistenceEventProcessor
from app.application.services.worker import EventWorker
from app.infrastructure.database.reader import SqlAlchemyLogEventReader
from app.infrastructure.database.repository import SqlAlchemyLogEventRepository
from app.infrastructure.database.runtime import (
    create_async_engine_from_settings,
    create_session_factory,
)
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
    database_engine: AsyncEngine | None = None,
    log_event_reader: LogEventReader | None = None,
) -> FastAPI:
    """Build one explicitly owned application runtime."""
    active_settings = settings or get_settings()
    configure_logging(active_settings)
    queue = event_queue or InMemoryEventQueue(active_settings.event_queue_max_size)
    active_engine: AsyncEngine | None = None
    owns_engine = False
    if event_processor is None:
        active_engine = database_engine or create_async_engine_from_settings(
            active_settings
        )
        owns_engine = database_engine is None
        session_factory = create_session_factory(active_engine)
        repository = SqlAlchemyLogEventRepository(session_factory)
        processor: EventProcessor = PersistenceEventProcessor(repository)
        if log_event_reader is None:
            log_event_reader = SqlAlchemyLogEventReader(session_factory)
    else:
        processor = event_processor
    ingestion_service = IngestionService(
        clock or SystemClock(),
        queue,
        **({"id_generator": event_id_factory} if event_id_factory is not None else {}),
    )
    worker = EventWorker(queue, processor)

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        worker_task: asyncio.Task[None] | None = None
        try:
            worker_task = asyncio.create_task(
                worker.run(), name="sentinelstream-event-worker"
            )
            application.state.worker_task = worker_task
            logger.info("event worker started")
            yield
        finally:
            try:
                if worker_task is not None:
                    try:
                        async with asyncio.timeout(
                            active_settings.worker_shutdown_timeout_seconds
                        ):
                            await queue.join()
                    except TimeoutError:
                        logger.warning(
                            "event queue did not drain within shutdown timeout"
                        )
                    finally:
                        worker_task.cancel()
                        with suppress(asyncio.CancelledError):
                            await worker_task
                        logger.info("event worker stopped")
            finally:
                if active_engine is not None and owns_engine:
                    await active_engine.dispose()
                    logger.info("database engine disposed")

    application = FastAPI(
        title=active_settings.application_name,
        version=active_settings.application_version,
        lifespan=lifespan,
    )
    application.state.settings = active_settings
    application.state.ingestion_service = ingestion_service
    application.state.log_event_reader = log_event_reader
    application.include_router(health_router)
    application.include_router(logs_router)
    return application


app = create_app()
