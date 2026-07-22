"""Tests for deterministic anomaly detector orchestration."""

from dataclasses import dataclass

import pytest

from app.application.anomalies.contracts import AnomalyRule
from app.application.anomalies.detector import RuleBasedAnomalyDetector
from app.application.anomalies.policy import DetectionPolicy
from app.application.anomalies.rules import build_default_anomaly_rules
from app.domain.anomalies import AnomalyFinding, AnomalySeverity, AnomalyType
from app.domain.logs import LogEvent, LogLevel
from tests.unit.application.anomalies.test_rules import EVENT_ID, event


@dataclass
class RecordingRule:
    rule_id: str
    result: AnomalyFinding | None
    calls: int = 0

    def evaluate(self, evaluated_event: LogEvent) -> AnomalyFinding | None:
        assert evaluated_event.event_id == EVENT_ID
        self.calls += 1
        return self.result


def finding(rule_id: str, severity: AnomalySeverity) -> AnomalyFinding:
    return AnomalyFinding(
        AnomalyType.ERROR_LEVEL, severity, rule_id, "Test", ("level=error",)
    )


def test_detector_rejects_empty_and_duplicate_rules() -> None:
    with pytest.raises(ValueError, match="at least one"):
        RuleBasedAnomalyDetector(())
    duplicate = RecordingRule("duplicate", None)
    with pytest.raises(ValueError, match="duplicate"):
        RuleBasedAnomalyDetector((duplicate, duplicate))


def test_detector_evaluates_each_rule_once_and_preserves_finding_order() -> None:
    first = RecordingRule("one", finding("one", AnomalySeverity.MEDIUM))
    second = RecordingRule("two", None)
    third = RecordingRule("three", finding("three", AnomalySeverity.CRITICAL))
    source = event(level=LogLevel.ERROR)
    before = source.to_dict()
    result = RuleBasedAnomalyDetector((first, second, third)).detect(source)
    assert [first.calls, second.calls, third.calls] == [1, 1, 1]
    assert tuple(item.rule_id for item in result.findings) == ("one", "three")
    assert result.highest_severity is AnomalySeverity.CRITICAL
    assert source.to_dict() == before


def test_detector_returns_non_anomalous_result() -> None:
    result = RuleBasedAnomalyDetector((RecordingRule("none", None),)).detect(event())
    assert result.event_id == EVENT_ID
    assert result.is_anomalous is False


def test_rule_errors_propagate_and_later_rule_is_not_silently_evaluated() -> None:
    class FaultyRule:
        rule_id = "faulty"

        def evaluate(self, evaluated_event: LogEvent) -> AnomalyFinding | None:
            raise RuntimeError("programming error")

    later = RecordingRule("later", None)
    with pytest.raises(RuntimeError, match="programming error"):
        RuleBasedAnomalyDetector((FaultyRule(), later)).detect(event())
    assert later.calls == 0


def test_default_factory_has_stable_unique_order() -> None:
    rules = build_default_anomaly_rules(DetectionPolicy())
    assert tuple(rule.rule_id for rule in rules) == (
        "single_event.error_level.v1",
        "single_event.server_error_status.v1",
        "single_event.exception_present.v1",
        "single_event.high_latency.v1",
    )
    assert len({rule.rule_id for rule in rules}) == len(rules)


def test_one_event_produces_all_distinct_findings_in_default_order() -> None:
    source = event(
        level=LogLevel.CRITICAL,
        status_code=575,
        exception_type="TimeoutError",
        exception_message="sensitive stack detail",
        latency_ms=6000,
    )
    detector = RuleBasedAnomalyDetector(build_default_anomaly_rules(DetectionPolicy()))
    result = detector.detect(source)
    assert tuple(item.anomaly_type for item in result.findings) == tuple(AnomalyType)
    assert result.highest_severity is AnomalySeverity.CRITICAL
    combined_evidence = " ".join(
        item for finding in result.findings for item in finding.evidence
    )
    assert source.message not in combined_evidence
    assert "sensitive stack detail" not in combined_evidence
    assert "secret" not in combined_evidence


def accepts_rule(rule: AnomalyRule) -> str:
    return rule.rule_id


def test_rule_protocol_is_structurally_satisfied() -> None:
    assert accepts_rule(RecordingRule("structural", None)) == "structural"
