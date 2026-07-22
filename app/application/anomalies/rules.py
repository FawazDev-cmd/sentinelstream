"""Built-in deterministic rules for a single trusted log event."""

from dataclasses import dataclass

from app.application.anomalies.contracts import AnomalyRule
from app.application.anomalies.policy import DetectionPolicy
from app.domain.anomalies import AnomalyFinding, AnomalySeverity, AnomalyType
from app.domain.logs import LogEvent, LogLevel


@dataclass(frozen=True, slots=True)
class ErrorLevelRule:
    rule_id = "single_event.error_level.v1"

    def evaluate(self, event: LogEvent) -> AnomalyFinding | None:
        severity = {
            LogLevel.ERROR: AnomalySeverity.HIGH,
            LogLevel.CRITICAL: AnomalySeverity.CRITICAL,
        }.get(event.level)
        if severity is None:
            return None
        return AnomalyFinding(
            AnomalyType.ERROR_LEVEL,
            severity,
            self.rule_id,
            "Error-level log event",
            (f"level={event.level.value.lower()}",),
        )


@dataclass(frozen=True, slots=True)
class ServerErrorStatusRule:
    policy: DetectionPolicy
    rule_id = "single_event.server_error_status.v1"

    def evaluate(self, event: LogEvent) -> AnomalyFinding | None:
        status = event.status_code
        if status is None or status < self.policy.server_error_min_status:
            return None
        severity = (
            AnomalySeverity.CRITICAL
            if status >= self.policy.critical_server_error_min_status
            else AnomalySeverity.HIGH
        )
        return AnomalyFinding(
            AnomalyType.SERVER_ERROR_STATUS,
            severity,
            self.rule_id,
            "Server error response",
            (
                f"status_code={status}",
                f"threshold_status={self.policy.server_error_min_status}",
            ),
        )


@dataclass(frozen=True, slots=True)
class ExceptionPresentRule:
    rule_id = "single_event.exception_present.v1"

    def evaluate(self, event: LogEvent) -> AnomalyFinding | None:
        evidence: list[str] = []
        if event.exception_type is not None:
            evidence.append(f"exception_type={event.exception_type}")
        if event.exception_message is not None:
            evidence.append("exception_message_present=true")
        if not evidence:
            return None
        return AnomalyFinding(
            AnomalyType.EXCEPTION_PRESENT,
            AnomalySeverity.HIGH,
            self.rule_id,
            "Exception information present",
            tuple(evidence),
        )


@dataclass(frozen=True, slots=True)
class HighLatencyRule:
    policy: DetectionPolicy
    rule_id = "single_event.high_latency.v1"

    def evaluate(self, event: LogEvent) -> AnomalyFinding | None:
        latency = event.latency_ms
        if latency is None or latency < self.policy.high_latency_threshold_ms:
            return None
        severity = (
            AnomalySeverity.CRITICAL
            if latency >= self.policy.critical_latency_threshold_ms
            else AnomalySeverity.MEDIUM
        )
        return AnomalyFinding(
            AnomalyType.HIGH_LATENCY,
            severity,
            self.rule_id,
            "High request latency",
            (
                f"latency_ms={latency:g}",
                f"threshold_ms={self.policy.high_latency_threshold_ms:g}",
            ),
        )


def build_default_anomaly_rules(
    policy: DetectionPolicy,
) -> tuple[AnomalyRule, ...]:
    return (
        ErrorLevelRule(),
        ServerErrorStatusRule(policy),
        ExceptionPresentRule(),
        HighLatencyRule(policy),
    )
