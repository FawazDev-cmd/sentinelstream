import asyncio
import math

import pytest
from pydantic import ValidationError

from app.infrastructure.database.runtime import (
    create_async_engine_from_settings,
    create_session_factory,
)
from app.shared.config import Settings

URL = "postgresql+asyncpg://user:password@localhost:5432/sentinelstream_test"


def test_engine_and_session_factory_follow_settings_without_logging_url(
    caplog: pytest.LogCaptureFixture,
) -> None:
    settings = Settings(database_url=URL, database_echo=True)
    engine = create_async_engine_from_settings(settings)
    factory = create_session_factory(engine)
    assert engine.url.drivername == "postgresql+asyncpg"
    assert engine.echo is True
    assert factory.kw["expire_on_commit"] is False
    assert URL not in caplog.text
    asyncio.run(engine.dispose())


@pytest.mark.parametrize("url", ["", "   "])
def test_blank_database_url_is_rejected(url: str) -> None:
    with pytest.raises(ValidationError):
        Settings(database_url=url)


@pytest.mark.parametrize(("raw", "expected"), [("true", True), ("false", False)])
def test_database_echo_parses_boolean(raw: str, expected: bool) -> None:
    assert Settings(database_echo=raw).database_echo is expected  # type: ignore[arg-type]


@pytest.mark.parametrize("timeout", [0, -1, math.inf, math.nan])
def test_existing_timeout_validation_remains(timeout: float) -> None:
    with pytest.raises(ValidationError):
        Settings(worker_shutdown_timeout_seconds=timeout)
