"""Deterministic orchestration over an explicitly ordered rule collection."""

from collections.abc import Sequence

from app.application.anomalies.contracts import AnomalyRule
from app.domain.anomalies import DetectionResult
from app.domain.logs import LogEvent


class RuleBasedAnomalyDetector:
    def __init__(self, rules: Sequence[AnomalyRule]) -> None:
        self._rules = tuple(rules)
        if not self._rules:
            raise ValueError("at least one anomaly rule is required")
        rule_ids = tuple(rule.rule_id for rule in self._rules)
        if any(not rule_id.strip() for rule_id in rule_ids):
            raise ValueError("rule IDs must not be blank")
        if len(set(rule_ids)) != len(rule_ids):
            raise ValueError("duplicate anomaly rule IDs are not allowed")

    def detect(self, event: LogEvent) -> DetectionResult:
        findings = tuple(
            finding
            for rule in self._rules
            if (finding := rule.evaluate(event)) is not None
        )
        return DetectionResult(event_id=event.event_id, findings=findings)
