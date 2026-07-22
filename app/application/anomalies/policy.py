"""Validated immutable configuration for deterministic anomaly rules."""

import math
from dataclasses import dataclass

from app.shared.config import Settings


@dataclass(frozen=True, slots=True)
class DetectionPolicy:
    high_latency_threshold_ms: float = 1_000.0
    critical_latency_threshold_ms: float = 5_000.0
    server_error_min_status: int = 500
    critical_server_error_min_status: int = 550

    def __post_init__(self) -> None:
        for name in ("high_latency_threshold_ms", "critical_latency_threshold_ms"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise TypeError(f"{name} must be a number")
            if not math.isfinite(value) or value <= 0:
                raise ValueError(f"{name} must be finite and positive")
            object.__setattr__(self, name, float(value))
        if self.critical_latency_threshold_ms < self.high_latency_threshold_ms:
            raise ValueError(
                "critical_latency_threshold_ms must be greater than or equal to "
                "high_latency_threshold_ms"
            )
        for name in ("server_error_min_status", "critical_server_error_min_status"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int):
                raise TypeError(f"{name} must be an integer")
        if not 500 <= self.server_error_min_status <= 599:
            raise ValueError("server_error_min_status must be between 500 and 599")
        if (
            not self.server_error_min_status
            <= self.critical_server_error_min_status
            <= 599
        ):
            raise ValueError(
                "critical_server_error_min_status must be between "
                "server_error_min_status and 599"
            )


def detection_policy_from_settings(settings: Settings) -> DetectionPolicy:
    return DetectionPolicy(
        high_latency_threshold_ms=settings.high_latency_threshold_ms,
        critical_latency_threshold_ms=settings.critical_latency_threshold_ms,
        server_error_min_status=settings.server_error_min_status,
        critical_server_error_min_status=settings.critical_server_error_min_status,
    )
