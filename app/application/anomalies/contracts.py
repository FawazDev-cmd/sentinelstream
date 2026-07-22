"""Narrow synchronous contracts for single-event anomaly detection."""

from typing import Protocol

from app.domain.anomalies import AnomalyFinding, DetectionResult
from app.domain.logs import LogEvent


class AnomalyRule(Protocol):
    @property
    def rule_id(self) -> str: ...

    def evaluate(self, event: LogEvent) -> AnomalyFinding | None: ...


class AnomalyDetector(Protocol):
    def detect(self, event: LogEvent) -> DetectionResult: ...
