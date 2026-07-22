"""Persist trusted events, with optional deterministic anomaly detection."""

import logging

from app.application.anomalies import AnomalyDetector
from app.application.contracts.detection_persistence import DetectionPersistence
from app.application.contracts.repository import LogEventRepository
from app.application.exceptions import DetectionResultEventMismatchError
from app.application.incidents.generation import (
    GenerateIncidents,
    IncidentGenerationRequest,
)
from app.domain.logs import LogEvent

logger = logging.getLogger(__name__)


class PersistenceEventProcessor:
    """Legacy event-only processor retained for the existing repository boundary."""

    def __init__(self, repository: LogEventRepository) -> None:
        self._repository = repository

    async def process(self, event: LogEvent) -> None:
        await self._repository.add(event)
        logger.debug(
            "log event persisted event_id=%s service=%s environment=%s level=%s",
            event.event_id,
            event.service,
            event.environment,
            event.level.value,
        )


class DetectAndPersistLogEventProcessor:
    """Detect once, validate the result, then persist atomically."""

    def __init__(
        self,
        detector: AnomalyDetector,
        persistence: DetectionPersistence,
        incident_generator: GenerateIncidents | None = None,
    ) -> None:
        self._detector = detector
        self._persistence = persistence
        self._incident_generator = incident_generator

    async def process(self, event: LogEvent) -> None:
        result = self._detector.detect(event)
        if result.event_id != event.event_id:
            raise DetectionResultEventMismatchError(
                "detection result event ID does not match source event ID"
            )
        await self._persistence.persist(event, result.findings)
        if result.findings and self._incident_generator is not None:
            await self._incident_generator.execute(
                IncidentGenerationRequest(event.timestamp, event.timestamp)
            )
        logger.debug(
            "event detection persisted event_id=%s finding_count=%d "
            "highest_severity=%s",
            event.event_id,
            len(result.findings),
            result.highest_severity.value if result.highest_severity else None,
        )
