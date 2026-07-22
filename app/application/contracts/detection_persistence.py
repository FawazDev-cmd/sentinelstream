"""Transactional persistence boundary for a detected log event."""

from collections.abc import Sequence
from typing import Protocol

from app.domain.anomalies import AnomalyFinding
from app.domain.logs import LogEvent


class DetectionPersistence(Protocol):
    async def persist(
        self, event: LogEvent, findings: Sequence[AnomalyFinding]
    ) -> None: ...
