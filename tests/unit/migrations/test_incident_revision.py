"""Tests for the Day 12 incident-table Alembic revision."""

import importlib.util
from pathlib import Path
from types import ModuleType
from typing import Any

from sqlalchemy import CheckConstraint, ForeignKeyConstraint, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PG_UUID

from alembic import op

ROOT = Path(__file__).parents[3]
PATH = ROOT / "alembic" / "versions" / "20260722_0003_create_incident_tables.py"
INCIDENT_INDEXES = {
    "ix_incidents_started_at",
    "ix_incidents_last_seen_at",
    "ix_incidents_highest_severity",
    "ix_incidents_service",
    "ix_incidents_environment",
    "ix_incidents_anomaly_type",
}


def revision() -> ModuleType:
    spec = importlib.util.spec_from_file_location("incident_revision", PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_revision_chain_and_metadata() -> None:
    module = revision()
    assert (
        module.revision == "20260722_0003" and module.down_revision == "20260722_0002"
    )
    assert module.branch_labels is None and module.depends_on is None


def test_upgrade_creates_only_incident_tables_constraints_and_indexes(
    monkeypatch: Any,
) -> None:
    module = revision()
    tables: dict[str, tuple[Any, ...]] = {}
    indexes: dict[str, tuple[str, list[str]]] = {}
    monkeypatch.setattr(
        op, "create_table", lambda name, *items: tables.setdefault(name, items)
    )
    monkeypatch.setattr(
        op,
        "create_index",
        lambda name, table, columns, **kwargs: indexes.setdefault(
            name, (table, columns)
        ),
    )
    module.upgrade()
    assert set(tables) == {"incidents", "incident_findings"}
    incident_columns = {
        item.name: item for item in tables["incidents"] if hasattr(item, "type")
    }
    membership_columns = {
        item.name: item for item in tables["incident_findings"] if hasattr(item, "type")
    }
    assert isinstance(incident_columns["id"].type, PG_UUID)
    assert isinstance(membership_columns["incident_id"].type, PG_UUID)
    assert all(
        column.nullable is False
        for column in (*incident_columns.values(), *membership_columns.values())
    )
    incident_checks = {
        item.name for item in tables["incidents"] if isinstance(item, CheckConstraint)
    }
    membership_checks = {
        item.name
        for item in tables["incident_findings"]
        if isinstance(item, CheckConstraint)
    }
    assert incident_checks == {
        "ck_incidents_finding_count",
        "ck_incidents_occurrence_range",
    }
    assert membership_checks == {"ck_incident_findings_position"}
    foreign_keys = [
        item
        for item in tables["incident_findings"]
        if isinstance(item, ForeignKeyConstraint)
    ]
    assert {
        (item.elements[0].target_fullname, item.ondelete) for item in foreign_keys
    } == {("incidents.id", "CASCADE"), ("anomaly_findings.id", "RESTRICT")}
    unique = {
        item.name
        for item in tables["incident_findings"]
        if isinstance(item, UniqueConstraint)
    }
    assert unique == {
        "uq_incident_findings_finding",
        "uq_incident_findings_incident_position",
    }
    assert set(indexes) == INCIDENT_INDEXES and all(
        table == "incidents" for table, _ in indexes.values()
    )


def test_downgrade_removes_only_incident_objects(monkeypatch: Any) -> None:
    module = revision()
    tables: list[str] = []
    indexes: list[tuple[str, str | None]] = []
    monkeypatch.setattr(op, "drop_table", tables.append)
    monkeypatch.setattr(
        op,
        "drop_index",
        lambda name, table_name=None: indexes.append((name, table_name)),
    )
    module.downgrade()
    assert tables == ["incident_findings", "incidents"]
    assert {name for name, _ in indexes} == INCIDENT_INDEXES
    assert all(table == "incidents" for _, table in indexes)
