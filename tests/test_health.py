"""Tests for the Day 1 application foundation."""

import io
import json
import logging

from fastapi.testclient import TestClient

from app.application.services.processor import LoggingEventProcessor
from app.monitoring.logging import configure_logging
from app.presentation.api.main import create_app
from app.shared.config import Settings


def test_health_returns_injected_service_identity(client: TestClient) -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "SentinelStream Test",
        "version": "9.8.7",
    }


def test_application_factory_accepts_settings(test_settings: Settings) -> None:
    application = create_app(test_settings, event_processor=LoggingEventProcessor())

    assert application.title == test_settings.application_name
    assert application.version == test_settings.application_version
    assert application.state.settings is test_settings


def test_repeated_setup_does_not_multiply_handlers(test_settings: Settings) -> None:
    root_logger = logging.getLogger()
    configure_logging(test_settings)
    count_after_first_setup = len(root_logger.handlers)

    configure_logging(test_settings)
    create_app(test_settings, event_processor=LoggingEventProcessor())
    create_app(test_settings, event_processor=LoggingEventProcessor())

    assert len(root_logger.handlers) == count_after_first_setup


def test_json_logging_emits_valid_json(test_settings: Settings) -> None:
    output = io.StringIO()
    configure_logging(test_settings, stream=output)

    logging.getLogger("sentinelstream.test").info("foundation ready")

    payload = json.loads(output.getvalue())
    assert payload["level"] == "INFO"
    assert payload["logger"] == "sentinelstream.test"
    assert payload["message"] == "foundation ready"
    assert payload["timestamp"].endswith("+00:00")
