"""Tests for deterministic adjacent-gap incident grouping."""

from datetime import UTC, datetime, timedelta, timezone
from uuid import UUID

import pytest

from app.application.incidents import (
    DeterministicIncidentGrouper,
    DuplicateIncidentGroupingFindingError,
    IncidentGroupingInput,
    IncidentGroupingPolicy,
)
from app.application.queries.anomalies import PersistedAnomalyFinding
from app.domain.anomalies import AnomalySeverity, AnomalyType
from app.domain.incidents import IncidentCandidate

BASE = datetime(2026, 7, 22, 12, tzinfo=UTC)


def grouped_input(
    number: int,
    minute: float,
    *,
    service: str = "payments-api",
    environment: str = "production",
    anomaly_type: AnomalyType = AnomalyType.HIGH_LATENCY,
    severity: AnomalySeverity = AnomalySeverity.MEDIUM,
    event_id: UUID | None = None,
    created_offset: int = 0,
    rule_id: str | None = None,
) -> IncidentGroupingInput:
    event_time = BASE + timedelta(minutes=minute)
    finding = PersistedAnomalyFinding(
        id=UUID(int=number),
        event_id=event_id or UUID(int=1000 + number),
        anomaly_type=anomaly_type,
        severity=severity,
        rule_id=rule_id or f"rule.{number}.v1",
        title="Finding",
        evidence=(f"number={number}",),
        created_at=event_time + timedelta(seconds=created_offset),
    )
    return IncidentGroupingInput(finding, service, environment, event_time)


def group(
    inputs: tuple[IncidentGroupingInput, ...],
    policy: IncidentGroupingPolicy | None = None,
) -> tuple[IncidentCandidate, ...]:
    return DeterministicIncidentGrouper(policy or IncidentGroupingPolicy()).group(
        inputs
    )


def test_empty_single_and_two_related_findings() -> None:
    assert group(()) == ()
    assert group((grouped_input(1, 0),)) == ()
    result = group((grouped_input(1, 0), grouped_input(2, 4)))
    assert len(result) == 1 and result[0].finding_count == 2
    assert result[0].started_at == BASE and result[0].last_seen_at == BASE + timedelta(
        minutes=4
    )


def test_exact_boundary_adjacent_chain_and_greater_gap_semantics() -> None:
    exact = group((grouped_input(1, 0), grouped_input(2, 5)))
    assert len(exact) == 1
    chain = group((grouped_input(1, 0), grouped_input(2, 4), grouped_input(3, 8)))
    assert len(chain) == 1 and chain[0].finding_count == 3
    split = group((grouped_input(1, 0), grouped_input(2, 4), grouped_input(3, 10)))
    assert len(split) == 1 and split[0].finding_ids == (UUID(int=1), UUID(int=2))
    micro_split = group((grouped_input(1, 0), grouped_input(2, 5 + 1 / 60_000_000)))
    assert micro_split == ()


@pytest.mark.parametrize("difference", ["service", "environment", "anomaly_type"])
def test_partition_fields_prevent_grouping(difference: str) -> None:
    kwargs: dict[str, object] = {
        "service": "other" if difference == "service" else "payments-api",
        "environment": "staging" if difference == "environment" else "production",
        "anomaly_type": AnomalyType.ERROR_LEVEL
        if difference == "anomaly_type"
        else AnomalyType.HIGH_LATENCY,
    }
    assert group((grouped_input(1, 0), grouped_input(2, 1, **kwargs))) == ()  # type: ignore[arg-type]


def test_severity_rule_id_and_duplicate_event_id_do_not_partition() -> None:
    event_id = UUID(int=500)
    result = group(
        (
            grouped_input(
                1, 0, severity=AnomalySeverity.MEDIUM, event_id=event_id, rule_id="one"
            ),
            grouped_input(
                2,
                1,
                severity=AnomalySeverity.CRITICAL,
                event_id=event_id,
                rule_id="two",
            ),
        )
    )
    candidate = result[0]
    assert candidate.highest_severity is AnomalySeverity.CRITICAL
    assert candidate.event_ids == (event_id, event_id)
    assert candidate.rule_ids == ("one", "two")


def test_input_order_independence_and_aligned_occurrence_order() -> None:
    values = (
        grouped_input(3, 2, rule_id="three"),
        grouped_input(1, 0, rule_id="one"),
        grouped_input(2, 1, rule_id="two"),
    )
    expected = group(values)
    assert (
        expected
        == group(tuple(reversed(values)))
        == group((values[1], values[2], values[0]))
    )
    candidate = expected[0]
    assert candidate.finding_ids == (UUID(int=1), UUID(int=2), UUID(int=3))
    assert candidate.rule_ids == ("one", "two", "three")
    assert candidate.event_ids == (UUID(int=1001), UUID(int=1002), UUID(int=1003))


def test_persistence_timestamp_then_uuid_break_occurrence_ties() -> None:
    values = (
        grouped_input(3, 0, created_offset=2),
        grouped_input(2, 0, created_offset=1),
        grouped_input(1, 0, created_offset=1),
    )
    assert group(values)[0].finding_ids == (UUID(int=1), UUID(int=2), UUID(int=3))


def test_separate_clusters_minimum_and_custom_policy() -> None:
    values = (
        grouped_input(1, 0),
        grouped_input(2, 10),
        grouped_input(3, 11),
        grouped_input(4, 30),
        grouped_input(5, 31),
    )
    result = group(values)
    assert [item.finding_ids for item in result] == [
        (UUID(int=2), UUID(int=3)),
        (UUID(int=4), UUID(int=5)),
    ]
    custom = group(values[:3], IncidentGroupingPolicy(timedelta(minutes=15), 3))
    assert len(custom) == 1 and custom[0].finding_count == 3


def test_final_candidate_order_is_deterministic_across_partitions() -> None:
    values = (
        grouped_input(3, 0, service="z"),
        grouped_input(4, 1, service="z"),
        grouped_input(1, 0, service="a"),
        grouped_input(2, 1, service="a"),
    )
    result = group(values)
    assert [item.key.service for item in result] == ["a", "z"]


def test_duplicate_finding_id_is_rejected_before_output_without_sensitive_data() -> (
    None
):
    value = grouped_input(1, 0)
    with pytest.raises(DuplicateIncidentGroupingFindingError) as captured:
        group((value, value))
    assert str(value.finding.id) in str(captured.value)
    assert "number=1" not in str(captured.value)


def test_offsets_same_instant_group_and_large_input_is_deterministic() -> None:
    offset = timezone(timedelta(hours=2))
    first = grouped_input(1, 0)
    second = grouped_input(2, 0)
    second = IncidentGroupingInput(
        second.finding, second.service, second.environment, BASE.astimezone(offset)
    )
    assert len(group((first, second))) == 1
    values = tuple(grouped_input(number, number / 10) for number in range(1, 201))
    before = tuple(values)
    result = group(tuple(reversed(values)))
    assert result == group(values) and values == before
    assert result[0].finding_count == 200
    assert len(set(result[0].finding_ids)) == 200
