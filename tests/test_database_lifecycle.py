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


def test_default_runtime_builds_detection_pipeline_reader_worker_and_disposes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def scenario() -> None:
        engine = FakeEngine()
        session_factory = object()
        policy = object()
        rules = (object(), object(), object(), object())
        detector = object()
        persistence = object()
        constructed: dict[str, object] = {}
        monkeypatch.setattr(
            main,
            "create_async_engine_from_settings",
            lambda settings: cast(AsyncEngine, cast(Any, engine)),
        )
        monkeypatch.setattr(
            main, "create_session_factory", lambda active: session_factory
        )
        monkeypatch.setattr(
            main,
            "detection_policy_from_settings",
            lambda settings: constructed.setdefault("settings", settings) and policy,
        )
        monkeypatch.setattr(
            main,
            "build_default_anomaly_rules",
            lambda active_policy: (
                constructed.setdefault("policy", active_policy) and rules
            ),
        )
        monkeypatch.setattr(
            main,
            "RuleBasedAnomalyDetector",
            lambda active_rules: (
                constructed.setdefault("rules", active_rules) and detector
            ),
        )
        monkeypatch.setattr(
            main,
            "SqlAlchemyDetectionPersistence",
            lambda factory: (
                constructed.setdefault("session_factory", factory) and persistence
            ),
        )

        def processor(
            active_detector: object,
            active_persistence: object,
            active_generator: object,
        ) -> NoOpProcessor:
            constructed["detector"] = active_detector
            constructed["persistence"] = active_persistence
            constructed["incident_generator"] = active_generator
            return NoOpProcessor()

        monkeypatch.setattr(main, "DetectAndPersistLogEventProcessor", processor)
        monkeypatch.setattr(
            main,
            "SqlAlchemyLogEventReader",
            lambda factory: (
                constructed.setdefault("reader_factory", factory) and object()
            ),
        )
        monkeypatch.setattr(
            main,
            "SqlAlchemyAnomalyFindingReader",
            lambda factory: (
                constructed.setdefault("anomaly_reader_factory", factory) and object()
            ),
        )
        settings = Settings(environment="test")
        app = main.create_app(settings)
        async with app.router.lifespan_context(app):
            task = app.state.worker_task
            assert not task.done()
        incident_generator = cast(Any, constructed.pop("incident_generator"))
        assert incident_generator._reader._session_factory is session_factory
        assert incident_generator._persistence._session_factory is session_factory
        assert constructed == {
            "settings": settings,
            "policy": policy,
            "rules": rules,
            "session_factory": session_factory,
            "detector": detector,
            "persistence": persistence,
            "reader_factory": session_factory,
            "anomaly_reader_factory": session_factory,
        }
        assert len(rules) == 4 and app.state.log_event_reader is not None
        assert app.state.anomaly_finding_reader is not None
        assert engine.disposals == 1 and task.done()

    asyncio.run(scenario())


def test_injected_processor_bypasses_database_and_detection_creation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for name in (
        "create_async_engine_from_settings",
        "detection_policy_from_settings",
        "build_default_anomaly_rules",
        "RuleBasedAnomalyDetector",
        "SqlAlchemyDetectionPersistence",
    ):
        monkeypatch.setattr(
            main,
            name,
            lambda *args, _name=name: (_ for _ in ()).throw(
                AssertionError(f"{_name} called")
            ),
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
            main,
            "DetectAndPersistLogEventProcessor",
            lambda detector, persistence, generator: NoOpProcessor(),
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
            main,
            "DetectAndPersistLogEventProcessor",
            lambda detector, persistence, generator: processor,
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
