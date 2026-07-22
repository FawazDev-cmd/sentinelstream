"""Persist trusted events, with optional deterministic anomaly detection."""

import logging
from collections.abc import Callable
from datetime import timedelta
from time import monotonic

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
            extra={
                "processing_id": str(event.event_id),
                "service": event.service,
                "environment": event.environment,
            },
        )


class DetectAndPersistLogEventProcessor:
    """Detect, persist, and generate incidents with structured observability."""

    def __init__(
        self,
        detector: AnomalyDetector,
        persistence: DetectionPersistence,
        incident_generator: GenerateIncidents | None = None,
        incident_generation_lookback: timedelta = timedelta(hours=1),
        monotonic_clock: Callable[[], float] = monotonic,
    ) -> None:
        self._detector = detector
        self._persistence = persistence
        self._incident_generator = incident_generator
        if not isinstance(incident_generation_lookback, timedelta):
            raise TypeError("incident_generation_lookback must be a timedelta")
        if (
            not timedelta(seconds=1)
            <= incident_generation_lookback
            <= timedelta(days=1)
        ):
            raise ValueError(
                "incident_generation_lookback must be between one second and one day"
            )
        self._incident_generation_lookback = incident_generation_lookback
        self._monotonic_clock = monotonic_clock

    async def process(self, event: LogEvent) -> None:
        started = self._monotonic_clock()
        common = {
            "processing_id": str(event.event_id),
            "service": event.service,
            "environment": event.environment,
            "event_timestamp": event.timestamp.isoformat(),
        }
        stage = "anomaly_detection"
        logger.info(
            "processing_started",
            extra={**common, "lifecycle_event": "processing_started"},
        )
        try:
            result = self._detector.detect(event)
            if result.event_id != event.event_id:
                raise DetectionResultEventMismatchError(
                    "detection result event ID does not match source event ID"
                )
            logger.info(
                "anomaly_detection_completed",
                extra={
                    **common,
                    "lifecycle_event": "anomaly_detection_completed",
                    "anomaly_count": len(result.findings),
                },
            )
            stage = "anomaly_persistence"
            await self._persistence.persist(event, result.findings)
            logger.info(
                "log_persisted", extra={**common, "lifecycle_event": "log_persisted"}
            )
            logger.info(
                "anomaly_persisted",
                extra={
                    **common,
                    "lifecycle_event": "anomaly_persisted",
                    "anomaly_count": len(result.findings),
                },
            )
            incidents_generated = 0
            if result.findings and self._incident_generator is not None:
                stage = "incident_generation"
                logger.info(
                    "incident_generation_started",
                    extra={**common, "lifecycle_event": "incident_generation_started"},
                )
                generation = await self._incident_generator.execute(
                    IncidentGenerationRequest(
                        event.timestamp - self._incident_generation_lookback,
                        event.timestamp,
                    )
                )
                incidents_generated = generation.incidents_persisted
                logger.info(
                    "incident_generation_completed",
                    extra={
                        **common,
                        "lifecycle_event": "incident_generation_completed",
                        "incident_count": incidents_generated,
                    },
                )
            duration_ms = max(0.0, (self._monotonic_clock() - started) * 1000)
            logger.info(
                "processing_completed",
                extra={
                    **common,
                    "lifecycle_event": "processing_completed",
                    "anomaly_count": len(result.findings),
                    "incident_count": incidents_generated,
                    "logs_processed": 1,
                    "anomalies_detected": len(result.findings),
                    "incidents_generated": incidents_generated,
                    "processing_duration_ms": duration_ms,
                    "total_processing_duration_ms": duration_ms,
                    "outcome": "success",
                },
            )
        except Exception as error:
            duration_ms = max(0.0, (self._monotonic_clock() - started) * 1000)
            logger.error(
                "processing_failed",
                extra={
                    **common,
                    "lifecycle_event": "processing_failed",
                    "failure_stage": stage,
                    "exception_type": type(error).__name__,
                    "safe_error_message": "processing stage failed",
                    "processing_duration_ms": duration_ms,
                    "total_processing_duration_ms": duration_ms,
                    "outcome": "failure",
                },
            )
            raise
