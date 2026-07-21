"""Shared test fixtures."""

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from app.presentation.api.main import create_app
from app.shared.config import Settings


@pytest.fixture
def test_settings() -> Settings:
    return Settings(
        application_name="SentinelStream Test",
        application_version="9.8.7",
        environment="test",
        log_level="DEBUG",
        json_logging_enabled=True,
    )


@pytest.fixture
def client(test_settings: Settings) -> Iterator[TestClient]:
    with TestClient(create_app(test_settings)) as test_client:
        yield test_client
