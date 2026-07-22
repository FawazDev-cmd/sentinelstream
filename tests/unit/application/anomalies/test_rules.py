"""Tests for all built-in single-event anomaly rules."""

from datetime import UTC, datetime
from uuid import UUID

import pytest

from app.application.anomalies.policy import DetectionPolicy
from app.application.anomalies.rules import (
    ErrorLevelRule,
    ExceptionPresentRule,
    HighLatencyRule,
    ServerErrorStatusRule,
)
from app.domain.anomalies import AnomalySeverity, AnomalyType
from app.domain.logs import LogEvent, LogLevel

EVENT_ID = UUID("00000000-0000-0000-0000-000000000008")
POLICY = DetectionPolicy()
SECRET_MESSAGE = "customer token secret must never appear"


def event(**overrides: object) -> LogEvent:
    values: dict[str, object] = {
        "event_id": EVENT_ID,
        "timestamp": datetime(2026, 7, 22, 12, tzinfo=UTC),
        "received_at": datetime(2026, 7, 22, 12, tzinfo=UTC),
        "service": "payments",
        "environment": "test",
        "level": LogLevel.INFO,
        "message": SECRET_MESSAGE,
        "metadata": {"secret": SECRET_MESSAGE},
    }
    values.update(overrides)
    return LogEvent(**values)  # type: ignore[arg-type]


@pytest.mark.parametrize("level", [LogLevel.DEBUG, LogLevel.INFO, LogLevel.WARNING])
def test_error_level_rule_ignores_non_error_levels(level: LogLevel) -> None:
    assert ErrorLevelRule().evaluate(event(level=level)) is None


@pytest.mark.parametrize(
    ("level", "severity"),
    [
        (LogLevel.ERROR, AnomalySeverity.HIGH),
        (LogLevel.CRITICAL, AnomalySeverity.CRITICAL),
    ],
)
def test_error_level_rule_triggers_with_safe_evidence(
    level: LogLevel, severity: AnomalySeverity
) -> None:
    finding = ErrorLevelRule().evaluate(event(level=level))
    assert finding is not None
    assert finding.anomaly_type is AnomalyType.ERROR_LEVEL
    assert finding.severity is severity
    assert finding.evidence == (f"level={level.value.lower()}",)
    assert SECRET_MESSAGE not in " ".join(finding.evidence)


@pytest.mark.parametrize("status", [None, 499])
def test_server_error_rule_ignores_missing_or_lower_status(status: int | None) -> None:
    assert ServerErrorStatusRule(POLICY).evaluate(event(status_code=status)) is None


@pytest.mark.parametrize(
    ("status", "severity"),
    [
        (500, AnomalySeverity.HIGH),
        (503, AnomalySeverity.HIGH),
        (550, AnomalySeverity.CRITICAL),
        (599, AnomalySeverity.CRITICAL),
    ],
)
def test_server_error_rule_boundaries_and_safe_evidence(
    status: int, severity: AnomalySeverity
) -> None:
    finding = ServerErrorStatusRule(POLICY).evaluate(event(status_code=status))
    assert finding is not None
    assert finding.anomaly_type is AnomalyType.SERVER_ERROR_STATUS
    assert finding.severity is severity
    assert finding.evidence == (f"status_code={status}", "threshold_status=500")
    assert SECRET_MESSAGE not in " ".join(finding.evidence)


def test_exception_rule_ignores_event_without_exception_fields() -> None:
    assert ExceptionPresentRule().evaluate(event()) is None


@pytest.mark.parametrize(
    ("fields", "evidence"),
    [
        ({"exception_type": "TimeoutError"}, ("exception_type=TimeoutError",)),
        ({"exception_message": SECRET_MESSAGE}, ("exception_message_present=true",)),
        (
            {"exception_type": "TimeoutError", "exception_message": SECRET_MESSAGE},
            ("exception_type=TimeoutError", "exception_message_present=true"),
        ),
    ],
)
def test_exception_rule_presence_evidence_is_accurate_and_redacted(
    fields: dict[str, object], evidence: tuple[str, ...]
) -> None:
    finding = ExceptionPresentRule().evaluate(event(**fields))
    assert finding is not None
    assert finding.anomaly_type is AnomalyType.EXCEPTION_PRESENT
    assert finding.severity is AnomalySeverity.HIGH
    assert finding.evidence == evidence
    assert SECRET_MESSAGE not in " ".join(finding.evidence)


@pytest.mark.parametrize("latency", [None, 999.99])
def test_latency_rule_ignores_missing_or_lower_latency(latency: float | None) -> None:
    assert HighLatencyRule(POLICY).evaluate(event(latency_ms=latency)) is None


@pytest.mark.parametrize(
    ("latency", "severity", "expected_actual"),
    [
        (1000.0, AnomalySeverity.MEDIUM, "latency_ms=1000"),
        (2500.0, AnomalySeverity.MEDIUM, "latency_ms=2500"),
        (5000.0, AnomalySeverity.CRITICAL, "latency_ms=5000"),
        (9000.0, AnomalySeverity.CRITICAL, "latency_ms=9000"),
    ],
)
def test_latency_rule_boundaries_and_safe_evidence(
    latency: float, severity: AnomalySeverity, expected_actual: str
) -> None:
    finding = HighLatencyRule(POLICY).evaluate(event(latency_ms=latency))
    assert finding is not None
    assert finding.anomaly_type is AnomalyType.HIGH_LATENCY
    assert finding.severity is severity
    assert finding.evidence == (expected_actual, "threshold_ms=1000")
    assert SECRET_MESSAGE not in " ".join(finding.evidence)
