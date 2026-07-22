"""Small, typed standard-library logging configuration."""

import json
import logging
from datetime import UTC, datetime
from typing import TextIO

from app.shared.config import Settings

_HANDLER_MARKER = "_sentinelstream_handler"
_STRUCTURED_FIELDS = (
    "lifecycle_event",
    "processing_id",
    "service",
    "environment",
    "event_timestamp",
    "anomaly_count",
    "incident_count",
    "failure_stage",
    "exception_type",
    "safe_error_message",
    "logs_processed",
    "anomalies_detected",
    "incidents_generated",
    "processing_duration_ms",
    "total_processing_duration_ms",
    "outcome",
)


class JsonFormatter(logging.Formatter):
    """Format supported log record fields as one JSON object."""

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info is not None:
            payload["exception"] = self.formatException(record.exc_info)
        for field in _STRUCTURED_FIELDS:
            if hasattr(record, field):
                payload[field] = getattr(record, field)
        return json.dumps(payload, ensure_ascii=False)


def configure_logging(settings: Settings, stream: TextIO | None = None) -> None:
    """Configure the root logger without accumulating owned handlers."""
    root_logger = logging.getLogger()
    for handler in tuple(root_logger.handlers):
        if getattr(handler, _HANDLER_MARKER, False):
            root_logger.removeHandler(handler)
            handler.close()
    handler = logging.StreamHandler(stream)
    setattr(handler, _HANDLER_MARKER, True)
    if settings.json_logging_enabled:
        handler.setFormatter(JsonFormatter())
    else:
        handler.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
        )
    root_logger.addHandler(handler)
    root_logger.setLevel(settings.log_level)
