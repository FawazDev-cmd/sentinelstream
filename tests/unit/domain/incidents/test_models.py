"""Tests for incident grouping values and policy invariants."""

from dataclasses import FrozenInstanceError
from datetime import UTC, datetime, timedelta, timezone
from typing import Any, cast
from uuid import UUID

import pytest

from app.application.incidents import IncidentGroupingInput, IncidentGroupingPolicy
from app.application.queries.anomalies import PersistedAnomalyFinding
from app.domain.anomalies import AnomalySeverity, AnomalyType
from app.domain.incidents import IncidentCandidate, IncidentGroupingKey
from app.domain.logs.models import ENVIRONMENT_MAX_LENGTH, SERVICE_MAX_LENGTH

MOMENT = datetime(2026, 7, 22, 12, tzinfo=UTC)


def finding() -> PersistedAnomalyFinding:
    return PersistedAnomalyFinding(
        UUID(int=1),
        UUID(int=2),
        AnomalyType.HIGH_LATENCY,
        AnomalySeverity.HIGH,
        "rule.v1",
        "High latency",
        ("latency_ms=2000",),
        MOMENT,
    )


def test_grouping_input_preserves_values_normalizes_utc_and_is_immutable() -> None:
    source = finding()
    offset = timezone(timedelta(hours=2))
    value = IncidentGroupingInput(
        source, " payments ", " production ", datetime(2026, 7, 22, 14, tzinfo=offset)
    )
    assert (
        value.finding is source
        and value.service == "payments"
        and value.environment == "production"
    )
    assert value.event_timestamp == MOMENT and source == finding()
    with pytest.raises(FrozenInstanceError):
        value.service = "other"  # type: ignore[misc]


@pytest.mark.parametrize(
    "kwargs",
    [
        {"service": " "},
        {"environment": " "},
        {"service": "x" * (SERVICE_MAX_LENGTH + 1)},
        {"environment": "x" * (ENVIRONMENT_MAX_LENGTH + 1)},
        {"event_timestamp": datetime(2026, 1, 1)},
    ],
)
def test_grouping_input_rejects_invalid_values(kwargs: dict[str, object]) -> None:
    values: dict[str, object] = {
        "finding": finding(),
        "service": "api",
        "environment": "prod",
        "event_timestamp": MOMENT,
    }
    values.update(kwargs)
    with pytest.raises((TypeError, ValueError)):
        IncidentGroupingInput(**values)  # type: ignore[arg-type]


def test_grouping_key_identity_is_only_service_environment_and_type() -> None:
    first = IncidentGroupingKey("api", "prod", AnomalyType.ERROR_LEVEL)
    assert first == IncidentGroupingKey("api", "prod", AnomalyType.ERROR_LEVEL)
    assert first != IncidentGroupingKey("other", "prod", AnomalyType.ERROR_LEVEL)
    assert first != IncidentGroupingKey("api", "stage", AnomalyType.ERROR_LEVEL)
    assert first != IncidentGroupingKey("api", "prod", AnomalyType.HIGH_LATENCY)
    with pytest.raises(FrozenInstanceError):
        first.service = "changed"  # type: ignore[misc]


def test_policy_defaults_boundaries_and_immutability() -> None:
    policy = IncidentGroupingPolicy()
    assert policy.maximum_gap == timedelta(minutes=5) and policy.minimum_findings == 2
    assert IncidentGroupingPolicy(timedelta(microseconds=1), 2).minimum_findings == 2
    assert IncidentGroupingPolicy(minimum_findings=10_000).minimum_findings == 10_000
    with pytest.raises(FrozenInstanceError):
        policy.minimum_findings = 3  # type: ignore[misc]


@pytest.mark.parametrize(
    "kwargs",
    [
        {"maximum_gap": timedelta(0)},
        {"maximum_gap": timedelta(seconds=-1)},
        {"minimum_findings": 1},
        {"minimum_findings": 10_001},
    ],
)
def test_policy_rejects_invalid_values(kwargs: dict[str, object]) -> None:
    with pytest.raises((TypeError, ValueError)):
        IncidentGroupingPolicy(**kwargs)  # type: ignore[arg-type]


def candidate(**overrides: object) -> IncidentCandidate:
    values: dict[str, object] = {
        "key": IncidentGroupingKey("api", "prod", AnomalyType.ERROR_LEVEL),
        "finding_ids": (UUID(int=1), UUID(int=2)),
        "event_ids": (UUID(int=11), UUID(int=12)),
        "rule_ids": ("one", "two"),
        "started_at": MOMENT,
        "last_seen_at": MOMENT,
        "finding_count": 2,
        "highest_severity": AnomalySeverity.CRITICAL,
    }
    values.update(overrides)
    return IncidentCandidate(**values)  # type: ignore[arg-type]


def test_candidate_validates_alignment_time_types_and_immutability() -> None:
    value = candidate()
    assert value.finding_count == len(value.finding_ids) == 2
    assert value.highest_severity is AnomalySeverity.CRITICAL
    with pytest.raises(FrozenInstanceError):
        value.finding_count = 3  # type: ignore[misc]
    for overrides in (
        {"finding_ids": ()},
        {"event_ids": (UUID(int=1),)},
        {"rule_ids": ("one",)},
        {"finding_count": 3},
        {"started_at": datetime(2026, 1, 1)},
        {"last_seen_at": datetime(2026, 1, 1)},
        {"started_at": MOMENT + timedelta(seconds=1), "last_seen_at": MOMENT},
        {"finding_ids": cast(Any, [UUID(int=1), UUID(int=2)])},
    ):
        with pytest.raises((TypeError, ValueError)):
            candidate(**overrides)
