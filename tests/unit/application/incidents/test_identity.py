"""Tests for deterministic incident UUIDv5 identity."""

from dataclasses import replace
from datetime import UTC, datetime, timedelta, timezone
from uuid import UUID

from app.application.incidents.identity import build_incident_id
from app.domain.anomalies import AnomalySeverity, AnomalyType
from app.domain.incidents import IncidentCandidate, IncidentGroupingKey

BASE = datetime(2026, 7, 22, 12, tzinfo=UTC)


def candidate(**overrides: object) -> IncidentCandidate:
    values: dict[str, object] = {
        "key": IncidentGroupingKey("payments", "production", AnomalyType.HIGH_LATENCY),
        "finding_ids": (UUID(int=1), UUID(int=2)),
        "event_ids": (UUID(int=101), UUID(int=102)),
        "rule_ids": ("one", "two"),
        "started_at": BASE,
        "last_seen_at": BASE + timedelta(minutes=4),
        "finding_count": 2,
        "highest_severity": AnomalySeverity.HIGH,
    }
    values.update(overrides)
    return IncidentCandidate(**values)  # type: ignore[arg-type]


def test_identity_is_stable_uuid5_and_non_mutating() -> None:
    value = candidate()
    before = value
    assert build_incident_id(value) == build_incident_id(value)
    assert build_incident_id(value).version == 5 and value == before


def test_every_identity_input_changes_id() -> None:
    original = candidate()
    variants = (
        replace(
            original,
            key=IncidentGroupingKey("orders", "production", AnomalyType.HIGH_LATENCY),
        ),
        replace(
            original,
            key=IncidentGroupingKey("payments", "staging", AnomalyType.HIGH_LATENCY),
        ),
        replace(
            original,
            key=IncidentGroupingKey("payments", "production", AnomalyType.ERROR_LEVEL),
        ),
        replace(original, started_at=BASE + timedelta(seconds=1)),
        replace(original, last_seen_at=BASE + timedelta(minutes=5)),
        replace(original, finding_ids=(UUID(int=1), UUID(int=3))),
        replace(original, finding_ids=tuple(reversed(original.finding_ids))),
    )
    assert all(
        build_incident_id(value) != build_incident_id(original) for value in variants
    )


def test_nonidentity_fields_do_not_change_id() -> None:
    original = candidate()
    assert build_incident_id(
        replace(original, highest_severity=AnomalySeverity.CRITICAL)
    ) == build_incident_id(original)
    assert build_incident_id(
        replace(original, rule_ids=("changed", "also-changed"))
    ) == build_incident_id(original)


def test_equivalent_utc_offsets_have_same_id() -> None:
    original = candidate()
    offset = timezone(timedelta(hours=2))
    equivalent = replace(
        original,
        started_at=original.started_at.astimezone(offset),
        last_seen_at=original.last_seen_at.astimezone(offset),
    )
    assert build_incident_id(equivalent) == build_incident_id(original)
