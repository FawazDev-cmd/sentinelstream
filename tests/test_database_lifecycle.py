import asyncio
from typing import Any, cast

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine

from app.application.services.processor import LoggingEventProcessor
from app.presentation.api import main
from app.shared.config import Settings


class FakeEngine:
    def __init__(self) -> None:
        self.disposals = 0

    async def dispose(self) -> None:
        self.disposals += 1


class NoOpProcessor:
    async def process(self, event: object) -> None:
        pass


def test_default_runtime_creates_persistence_processor_starts_worker_and_disposes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def scenario() -> None:
        engine = FakeEngine()
        processors: list[object] = []
        monkeypatch.setattr(
            main,
            "create_async_engine_from_settings",
            lambda settings: cast(AsyncEngine, cast(Any, engine)),
        )
        monkeypatch.setattr(
            main, "create_session_factory", lambda active_engine: cast(Any, object())
        )

        def processor(repository: object) -> NoOpProcessor:
            processors.append(repository)
            return NoOpProcessor()

        monkeypatch.setattr(main, "PersistenceEventProcessor", processor)
        app = main.create_app(Settings(environment="test"))
        async with app.router.lifespan_context(app):
            task = app.state.worker_task
            assert not task.done()
        assert len(processors) == 1
        assert engine.disposals == 1 and task.done()

    asyncio.run(scenario())


def test_injected_processor_bypasses_database_creation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        main,
        "create_async_engine_from_settings",
        lambda settings: (_ for _ in ()).throw(AssertionError("engine created")),
    )
    app = main.create_app(
        Settings(environment="test"), event_processor=LoggingEventProcessor()
    )

    async def scenario() -> None:
        async with app.router.lifespan_context(app):
            pass

    asyncio.run(scenario())


def test_external_engine_is_caller_owned(monkeypatch: pytest.MonkeyPatch) -> None:
    async def scenario() -> None:
        engine = FakeEngine()
        monkeypatch.setattr(
            main, "create_session_factory", lambda active_engine: cast(Any, object())
        )
        monkeypatch.setattr(
            main, "PersistenceEventProcessor", lambda repository: NoOpProcessor()
        )
        app = main.create_app(
            Settings(environment="test"),
            database_engine=cast(AsyncEngine, cast(Any, engine)),
        )
        async with app.router.lifespan_context(app):
            pass
        assert engine.disposals == 0

    asyncio.run(scenario())


def test_owned_engine_disposes_after_queue_drain_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class BlockingProcessor:
        def __init__(self) -> None:
            self.started = asyncio.Event()

        async def process(self, event: object) -> None:
            self.started.set()
            await asyncio.Future()

    async def scenario() -> None:
        from tests.test_lifespan import input_data

        engine = FakeEngine()
        processor = BlockingProcessor()
        monkeypatch.setattr(
            main,
            "create_async_engine_from_settings",
            lambda settings: cast(AsyncEngine, cast(Any, engine)),
        )
        monkeypatch.setattr(
            main, "create_session_factory", lambda active_engine: cast(Any, object())
        )
        monkeypatch.setattr(
            main, "PersistenceEventProcessor", lambda repository: processor
        )
        app = main.create_app(
            Settings(environment="test", worker_shutdown_timeout_seconds=0.01)
        )
        context = app.router.lifespan_context(app)
        await context.__aenter__()
        await app.state.ingestion_service.ingest(input_data())
        await asyncio.wait_for(processor.started.wait(), 0.2)
        await asyncio.wait_for(context.__aexit__(None, None, None), 0.2)
        assert engine.disposals == 1 and app.state.worker_task.cancelled()

    asyncio.run(scenario())


def test_application_runtime_has_no_schema_creation_symbol() -> None:
    assert not hasattr(main, "create_database_schema")
