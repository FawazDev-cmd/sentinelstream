"""Tests for the Day 9 anomaly-finding Alembic revision."""

import importlib.util
from pathlib import Path
from types import ModuleType
from typing import Any, cast

from sqlalchemy import DateTime, ForeignKeyConstraint, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID

from alembic import op
from app.infrastructure.database.models import AnomalyFindingRecord

ROOT = Path(__file__).parents[3]
REVISION_PATH = (
    ROOT / "alembic" / "versions" / "20260722_0002_create_anomaly_findings_table.py"
)
EXPECTED_INDEXES = {
    "ix_anomaly_findings_event_id",
    "ix_anomaly_findings_severity",
    "ix_anomaly_findings_anomaly_type",
    "ix_anomaly_findings_created_at",
}


def revision_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location("anomaly_revision", REVISION_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_revision_chain_has_exactly_two_ordered_revisions() -> None:
    files = sorted((ROOT / "alembic" / "versions").glob("*.py"))
    assert [path.name[:13] for path in files] == ["20260722_0001", "20260722_0002"]
    module = revision_module()
    assert module.revision == "20260722_0002"
    assert module.down_revision == "20260722_0001"
    assert module.branch_labels is None and module.depends_on is None


def test_upgrade_creates_anomaly_table_types_constraints_and_indexes(
    monkeypatch: Any,
) -> None:
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
    assert created["name"] == AnomalyFindingRecord.__tablename__ == "anomaly_findings"
    items = cast(tuple[Any, ...], created["items"])
    columns = {item.name: item for item in items if hasattr(item, "type")}
    assert set(columns) == {
        "id",
        "event_id",
        "anomaly_type",
        "severity",
        "rule_id",
        "title",
        "evidence",
        "created_at",
    }
    assert isinstance(columns["id"].type, PG_UUID) and columns["id"].type.as_uuid
    assert isinstance(columns["event_id"].type, PG_UUID)
    assert isinstance(columns["evidence"].type, JSONB)
    assert (
        isinstance(columns["created_at"].type, DateTime)
        and columns["created_at"].type.timezone
    )
    assert all(column.nullable is False for column in columns.values())
    foreign_key = next(item for item in items if isinstance(item, ForeignKeyConstraint))
    assert list(foreign_key.column_keys) == ["event_id"]
    assert [element.target_fullname for element in foreign_key.elements] == [
        "log_events.event_id"
    ]
    assert foreign_key.ondelete == "CASCADE"
    unique = next(item for item in items if isinstance(item, UniqueConstraint))
    assert unique.name == "uq_anomaly_findings_event_rule"
    assert list(unique._pending_colargs) == ["event_id", "rule_id"]
    assert set(indexes) == EXPECTED_INDEXES
    assert all(table == "anomaly_findings" for table, _ in indexes.values())


def test_downgrade_removes_only_anomaly_objects(monkeypatch: Any) -> None:
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
    assert all(table == "anomaly_findings" for _, table in indexes)
    assert tables == ["anomaly_findings"]
