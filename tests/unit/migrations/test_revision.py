import importlib.util
from pathlib import Path
from types import ModuleType
from typing import Any, cast

from sqlalchemy import DateTime
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID

from alembic import op
from app.infrastructure.database.models import LogEventRecord

ROOT = Path(__file__).parents[3]
VERSIONS = ROOT / "alembic" / "versions"
EXPECTED_COLUMNS = {
    "event_id",
    "timestamp",
    "received_at",
    "service",
    "environment",
    "level",
    "message",
    "exception_type",
    "exception_message",
    "latency_ms",
    "status_code",
    "trace_id",
    "request_id",
    "host",
    "metadata",
}
EXPECTED_INDEXES = {
    "ix_log_events_timestamp",
    "ix_log_events_received_at",
    "ix_log_events_service",
    "ix_log_events_environment",
    "ix_log_events_level",
    "ix_log_events_service_timestamp",
}


def revision_module() -> ModuleType:
    files = list(VERSIONS.glob("*.py"))
    assert len(files) == 1
    spec = importlib.util.spec_from_file_location("initial_revision", files[0])
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_exactly_one_initial_revision_with_upgrade_and_downgrade() -> None:
    module = revision_module()
    assert module.revision == "20260722_0001"
    assert (
        module.down_revision is None
        and module.branch_labels is None
        and module.depends_on is None
    )
    assert callable(module.upgrade) and callable(module.downgrade)


def test_upgrade_matches_orm_table_and_postgresql_types(monkeypatch: Any) -> None:
    module = revision_module()
    created: dict[str, object] = {}
    indexes: dict[str, tuple[str, list[str]]] = {}

    def create_table(name: str, *items: object) -> None:
        created["name"] = name
        created["items"] = items

    def create_index(
        name: str, table: str, columns: list[str], **kwargs: object
    ) -> None:
        indexes[name] = (table, columns)

    monkeypatch.setattr(op, "create_table", create_table)
    monkeypatch.setattr(op, "create_index", create_index)
    module.upgrade()
    assert created["name"] == LogEventRecord.__tablename__ == "log_events"
    columns = {
        item.name: item
        for item in cast(tuple[Any, ...], created["items"])
        if hasattr(item, "type")
    }
    assert set(columns) == EXPECTED_COLUMNS
    assert (
        isinstance(columns["event_id"].type, PG_UUID)
        and columns["event_id"].type.as_uuid
    )
    assert isinstance(columns["metadata"].type, JSONB)
    assert (
        isinstance(columns["timestamp"].type, DateTime)
        and columns["timestamp"].type.timezone
    )
    assert (
        isinstance(columns["received_at"].type, DateTime)
        and columns["received_at"].type.timezone
    )
    for name in {
        "event_id",
        "timestamp",
        "received_at",
        "service",
        "environment",
        "level",
        "message",
        "metadata",
    }:
        assert columns[name].nullable is False
    for name in EXPECTED_COLUMNS - {
        "event_id",
        "timestamp",
        "received_at",
        "service",
        "environment",
        "level",
        "message",
        "metadata",
    }:
        assert columns[name].nullable is True
    assert set(indexes) == EXPECTED_INDEXES
    assert indexes["ix_log_events_service_timestamp"] == (
        "log_events",
        ["service", "timestamp"],
    )


def test_downgrade_removes_only_revision_indexes_and_table(monkeypatch: Any) -> None:
    module = revision_module()
    indexes: list[tuple[str, str | None]] = []
    tables: list[str] = []
    monkeypatch.setattr(
        op,
        "drop_index",
        lambda name, table_name=None: indexes.append((name, table_name)),
    )
    monkeypatch.setattr(op, "drop_table", tables.append)
    module.downgrade()
    assert {name for name, _ in indexes} == EXPECTED_INDEXES
    assert all(table == "log_events" for _, table in indexes)
    assert tables == ["log_events"]
