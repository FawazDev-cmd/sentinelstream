"""Tests for immutable anomaly domain values."""

from dataclasses import FrozenInstanceError
from uuid import uuid4

import pytest

from app.domain.anomalies import (
    AnomalyFinding,
    AnomalySeverity,
    AnomalyType,
    DetectionResult,
)
from app.domain.anomalies.models import (
    EVIDENCE_ITEM_MAX_LENGTH,
    RULE_ID_MAX_LENGTH,
    TITLE_MAX_LENGTH,
)


def finding(
    severity: AnomalySeverity = AnomalySeverity.HIGH,
    rule_id: str = "test.rule.v1",
) -> AnomalyFinding:
    return AnomalyFinding(
        AnomalyType.ERROR_LEVEL, severity, rule_id, "Test finding", ("level=error",)
    )


def test_expected_anomaly_types_and_severities_are_stable() -> None:
    assert [item.value for item in AnomalyType] == [
        "error_level",
        "server_error_status",
        "exception_present",
        "high_latency",
    ]
    assert [item.value for item in AnomalySeverity] == [
        "low",
        "medium",
        "high",
        "critical",
    ]


def test_severity_rank_is_explicit_and_not_lexical() -> None:
    assert AnomalySeverity.CRITICAL.rank > AnomalySeverity.HIGH.rank
    assert AnomalySeverity.HIGH.rank > AnomalySeverity.MEDIUM.rank
    assert AnomalySeverity.MEDIUM.rank > AnomalySeverity.LOW.rank
    assert sorted(AnomalySeverity, key=lambda item: item.rank) == [
        AnomalySeverity.LOW,
        AnomalySeverity.MEDIUM,
        AnomalySeverity.HIGH,
        AnomalySeverity.CRITICAL,
    ]
    assert sorted(item.value for item in AnomalySeverity) != [
        item.value
        for item in sorted(AnomalySeverity, key=lambda severity: severity.rank)
    ]


def test_valid_finding_is_immutable_with_tuple_evidence() -> None:
    value = finding()
    assert value.evidence == ("level=error",)
    with pytest.raises(FrozenInstanceError):
        value.title = "changed"  # type: ignore[misc]
    with pytest.raises(TypeError):
        value.evidence[0] = "changed"  # type: ignore[index]


@pytest.mark.parametrize(
    ("kwargs", "error"),
    [
        ({"rule_id": " "}, ValueError),
        ({"title": " "}, ValueError),
        ({"evidence": ()}, ValueError),
        ({"evidence": ("",)}, ValueError),
        ({"rule_id": "r" * (RULE_ID_MAX_LENGTH + 1)}, ValueError),
        ({"title": "t" * (TITLE_MAX_LENGTH + 1)}, ValueError),
        ({"evidence": ("e" * (EVIDENCE_ITEM_MAX_LENGTH + 1),)}, ValueError),
        ({"evidence": ["mutable"]}, TypeError),
    ],
)
def test_finding_rejects_invalid_values(
    kwargs: dict[str, object], error: type[Exception]
) -> None:
    values: dict[str, object] = {
        "anomaly_type": AnomalyType.ERROR_LEVEL,
        "severity": AnomalySeverity.HIGH,
        "rule_id": "test.rule.v1",
        "title": "Test",
        "evidence": ("level=error",),
    }
    values.update(kwargs)
    with pytest.raises(error):
        AnomalyFinding(**values)  # type: ignore[arg-type]


def test_detection_result_empty_semantics_and_event_id() -> None:
    event_id = uuid4()
    result = DetectionResult(event_id, ())
    assert result.event_id == event_id
    assert result.is_anomalous is False
    assert result.highest_severity is None


def test_detection_result_preserves_order_and_calculates_highest() -> None:
    ordered = (
        finding(AnomalySeverity.MEDIUM, "one"),
        finding(AnomalySeverity.CRITICAL, "two"),
    )
    result = DetectionResult(uuid4(), ordered)
    assert result.is_anomalous is True
    assert result.findings == ordered
    assert result.highest_severity is AnomalySeverity.CRITICAL
    with pytest.raises(FrozenInstanceError):
        result.findings = ()  # type: ignore[misc]
