"""Stable anomaly classifications and explicitly ordered severities."""

from enum import StrEnum


class AnomalyType(StrEnum):
    ERROR_LEVEL = "error_level"
    SERVER_ERROR_STATUS = "server_error_status"
    EXCEPTION_PRESENT = "exception_present"
    HIGH_LATENCY = "high_latency"


class AnomalySeverity(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"

    @property
    def rank(self) -> int:
        return {
            AnomalySeverity.LOW: 1,
            AnomalySeverity.MEDIUM: 2,
            AnomalySeverity.HIGH: 3,
            AnomalySeverity.CRITICAL: 4,
        }[self]
