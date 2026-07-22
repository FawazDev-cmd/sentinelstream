import asyncio
from datetime import UTC, datetime
from uuid import UUID

import httpx

from app.application.services.ingestion import IngestionInput
from app.domain.logs import LogEvent
from app.infrastructure.queue.memory import InMemoryEventQueue
from app.presentation.api.main import create_app
from app.shared.config import Settings


class RecordingProcessor:
    def __init__(self) -> None:
        self.events: list[LogEvent] = []
        self.processed = asyncio.Event()

    async def process(self, event: LogEvent) -> None:
        self.events.append(event)
        self.processed.set()


class BlockingProcessor:
    def __init__(self) -> None:
        self.started = asyncio.Event()
        self.release = asyncio.Event()
        self.cancelled = False

    async def process(self, event: LogEvent) -> None:
        self.started.set()
        try:
            await self.release.wait()
        except asyncio.CancelledError:
            self.cancelled = True
            raise


def input_data() -> IngestionInput:
    return IngestionInput(
        timestamp=datetime(2026, 7, 22, tzinfo=UTC),
        service="api",
        environment="test",
        level="info",
        message="ready",
    )


def settings(timeout: float = 0.2) -> Settings:
    return Settings(environment="test", worker_shutdown_timeout_seconds=timeout)


def test_lifespan_starts_exactly_one_worker_and_processes_api_event() -> None:
    async def scenario() -> None:
        queue = InMemoryEventQueue(2)
        processor = RecordingProcessor()
        app = create_app(
            settings(),
            event_queue=queue,
            event_processor=processor,
            event_id_factory=lambda: UUID(int=1),
        )
        async with app.router.lifespan_context(app):
            worker_task = app.state.worker_task
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://test"
            ) as client:
                response = await client.post(
                    "/api/v1/logs",
                    json={
                        "timestamp": "2026-07-22T00:00:00Z",
                        "service": "api",
                        "environment": "test",
                        "level": "info",
                        "message": "ready",
                    },
                )
            await asyncio.wait_for(processor.processed.wait(), 0.2)
            assert response.status_code == 202
            assert app.state.worker_task is worker_task
            assert len(processor.events) == 1
        assert worker_task.done()

    asyncio.run(scenario())


def test_shutdown_waits_for_work_then_cancels_waiting_worker() -> None:
    async def scenario() -> None:
        queue = InMemoryEventQueue(1)
        processor = BlockingProcessor()
        app = create_app(settings(), event_queue=queue, event_processor=processor)
        context = app.router.lifespan_context(app)
        await context.__aenter__()
        await app.state.ingestion_service.ingest(input_data())
        await asyncio.wait_for(processor.started.wait(), 0.2)
        shutdown = asyncio.create_task(context.__aexit__(None, None, None))
        await asyncio.sleep(0)
        assert not shutdown.done()
        processor.release.set()
        await asyncio.wait_for(shutdown, 0.2)
        assert app.state.worker_task.cancelled()

    asyncio.run(scenario())


def test_shutdown_timeout_cancels_and_awaits_worker() -> None:
    async def scenario() -> None:
        queue = InMemoryEventQueue(1)
        processor = BlockingProcessor()
        app = create_app(settings(0.01), event_queue=queue, event_processor=processor)
        context = app.router.lifespan_context(app)
        await context.__aenter__()
        await app.state.ingestion_service.ingest(input_data())
        await processor.started.wait()
        await asyncio.wait_for(context.__aexit__(None, None, None), 0.2)
        assert processor.cancelled
        assert app.state.worker_task.cancelled()

    asyncio.run(scenario())


def test_processor_failure_does_not_prevent_clean_shutdown() -> None:
    class FailingProcessor:
        async def process(self, event: LogEvent) -> None:
            raise RuntimeError("failure")

    async def scenario() -> None:
        queue = InMemoryEventQueue(1)
        app = create_app(
            settings(), event_queue=queue, event_processor=FailingProcessor()
        )
        async with app.router.lifespan_context(app):
            await app.state.ingestion_service.ingest(input_data())
            await asyncio.wait_for(queue.join(), 0.2)
        assert app.state.worker_task.done()

    asyncio.run(scenario())
