"""Tests for detection policy and centralized settings conversion."""

import math

import pytest
from pydantic import ValidationError

from app.application.anomalies.policy import (
    DetectionPolicy,
    detection_policy_from_settings,
)
from app.shared.config import Settings


def test_policy_defaults_and_settings_conversion() -> None:
    policy = DetectionPolicy()
    assert policy == DetectionPolicy(1000.0, 5000.0, 500, 550)
    assert detection_policy_from_settings(Settings()) == policy


@pytest.mark.parametrize(
    "kwargs",
    [
        {"high_latency_threshold_ms": 0},
        {"high_latency_threshold_ms": -1},
        {"high_latency_threshold_ms": math.nan},
        {"critical_latency_threshold_ms": math.inf},
        {"high_latency_threshold_ms": 2000, "critical_latency_threshold_ms": 1000},
        {"server_error_min_status": 499},
        {"server_error_min_status": 600},
        {"server_error_min_status": 550, "critical_server_error_min_status": 549},
        {"critical_server_error_min_status": 600},
    ],
)
def test_policy_rejects_invalid_thresholds(kwargs: dict[str, object]) -> None:
    with pytest.raises((TypeError, ValueError)):
        DetectionPolicy(**kwargs)  # type: ignore[arg-type]


def test_policy_is_immutable() -> None:
    policy = DetectionPolicy()
    with pytest.raises(AttributeError):
        policy.high_latency_threshold_ms = 1  # type: ignore[misc]


def test_settings_environment_overrides_construct_policy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SENTINELSTREAM_HIGH_LATENCY_THRESHOLD_MS", "250")
    monkeypatch.setenv("SENTINELSTREAM_CRITICAL_LATENCY_THRESHOLD_MS", "750")
    monkeypatch.setenv("SENTINELSTREAM_SERVER_ERROR_MIN_STATUS", "501")
    monkeypatch.setenv("SENTINELSTREAM_CRITICAL_SERVER_ERROR_MIN_STATUS", "575")
    assert detection_policy_from_settings(Settings()) == DetectionPolicy(
        250, 750, 501, 575
    )


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("SENTINELSTREAM_HIGH_LATENCY_THRESHOLD_MS", "nan"),
        ("SENTINELSTREAM_CRITICAL_LATENCY_THRESHOLD_MS", "inf"),
        ("SENTINELSTREAM_SERVER_ERROR_MIN_STATUS", "499"),
    ],
)
def test_invalid_environment_overrides_fail_clearly(
    monkeypatch: pytest.MonkeyPatch, name: str, value: str
) -> None:
    monkeypatch.setenv(name, value)
    with pytest.raises(ValidationError):
        Settings()


def test_settings_reject_cross_field_threshold_ordering() -> None:
    with pytest.raises(ValidationError):
        Settings(high_latency_threshold_ms=2000, critical_latency_threshold_ms=1000)
    with pytest.raises(ValidationError):
        Settings(server_error_min_status=560, critical_server_error_min_status=550)
