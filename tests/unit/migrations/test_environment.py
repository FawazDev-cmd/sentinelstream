import runpy
from contextlib import nullcontext
from pathlib import Path
from typing import Any

import alembic.context
from alembic.config import Config

from app.infrastructure.database.migrations import resolve_migration_database_url
from app.shared.config import Settings

ROOT = Path(__file__).parents[3]
ENV_PATH = ROOT / "alembic" / "env.py"


def test_url_resolution_uses_validated_settings() -> None:
    url = "postgresql+asyncpg://user:secret@localhost/sentinelstream_test"
    assert resolve_migration_database_url(Settings(database_url=url)) == url


def test_ini_contains_only_harmless_placeholder() -> None:
    text = (ROOT / "alembic.ini").read_text(encoding="utf-8-sig")
    assert "placeholder:placeholder" in text
    assert "sentinelstream:sentinelstream" not in text


def configure_context(
    monkeypatch: Any, *, offline: bool
) -> tuple[dict[str, object], Any]:
    captured: dict[str, object] = {}
    config = Config(str(ROOT / "alembic.ini"))
    config.config_file_name = None
    monkeypatch.setattr(alembic.context, "config", config, raising=False)
    monkeypatch.setattr(alembic.context, "is_offline_mode", lambda: offline)
    monkeypatch.setattr(
        alembic.context, "configure", lambda **kwargs: captured.update(kwargs)
    )
    monkeypatch.setattr(alembic.context, "begin_transaction", nullcontext)
    monkeypatch.setattr(alembic.context, "run_migrations", lambda: None)
    return captured, config


def test_offline_mode_receives_resolved_url_without_printing(
    monkeypatch: Any, capsys: Any
) -> None:
    expected = "postgresql+asyncpg://user:secret@localhost/sentinelstream_test"
    monkeypatch.setenv("SENTINELSTREAM_DATABASE_URL", expected)
    captured, _ = configure_context(monkeypatch, offline=True)
    runpy.run_path(str(ENV_PATH))
    assert captured["url"] == expected
    output = capsys.readouterr()
    assert expected not in output.out and expected not in output.err


def test_online_mode_uses_async_engine_and_disposes(monkeypatch: Any) -> None:
    captured, _ = configure_context(monkeypatch, offline=False)

    class Connection:
        async def __aenter__(self) -> "Connection":
            return self

        async def __aexit__(self, *args: object) -> None:
            pass

        async def run_sync(self, function: Any) -> None:
            function(self)

    class Engine:
        def __init__(self) -> None:
            self.disposed = False

        def connect(self) -> Connection:
            return Connection()

        async def dispose(self) -> None:
            self.disposed = True

    engine = Engine()
    monkeypatch.setattr(
        "sqlalchemy.ext.asyncio.async_engine_from_config",
        lambda *args, **kwargs: engine,
    )
    runpy.run_path(str(ENV_PATH))
    assert engine.disposed
    assert "connection" in captured
