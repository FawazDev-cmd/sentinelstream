"""Focused conversion between domain values and ORM records."""

import copy
from collections.abc import Mapping
from datetime import datetime
from typing import cast
from uuid import UUID, uuid4

from app.domain.anomalies import AnomalyFinding
from app.domain.logs import LogEvent, LogLevel
from app.domain.logs.models import FrozenJsonValue, JsonValue
from app.infrastructure.database.models import AnomalyFindingRecord, LogEventRecord


def _mutable_json(value: FrozenJsonValue) -> JsonValue:
    if isinstance(value, Mapping):
        return {key: _mutable_json(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_mutable_json(item) for item in value]
    return value


def map_log_event(event: LogEvent) -> LogEventRecord:
    metadata = cast(dict[str, JsonValue], _mutable_json(event.metadata))
    return LogEventRecord(
        event_id=event.event_id,
        timestamp=event.timestamp,
        received_at=event.received_at,
        service=event.service,
        environment=event.environment,
        level=event.level.value,
        message=event.message,
        exception_type=event.exception_type,
        exception_message=event.exception_message,
        latency_ms=event.latency_ms,
        status_code=event.status_code,
        trace_id=event.trace_id,
        request_id=event.request_id,
        host=event.host,
        event_metadata=metadata,
    )


def map_anomaly_finding(
    event_id: UUID,
    finding: AnomalyFinding,
    created_at: datetime,
    *,
    persistence_id: UUID | None = None,
) -> AnomalyFindingRecord:
    return AnomalyFindingRecord(
        id=persistence_id or uuid4(),
        event_id=event_id,
        anomaly_type=finding.anomaly_type.value,
        severity=finding.severity.value,
        rule_id=finding.rule_id,
        title=finding.title,
        evidence=list(finding.evidence),
        created_at=created_at,
    )


def map_log_event_record(record: LogEventRecord) -> LogEvent:
    metadata = cast(dict[str, FrozenJsonValue], copy.deepcopy(record.event_metadata))
    return LogEvent(
        event_id=record.event_id,
        timestamp=record.timestamp,
        received_at=record.received_at,
        service=record.service,
        environment=record.environment,
        level=LogLevel(record.level),
        message=record.message,
        exception_type=record.exception_type,
        exception_message=record.exception_message,
        latency_ms=record.latency_ms,
        status_code=record.status_code,
        trace_id=record.trace_id,
        request_id=record.request_id,
        host=record.host,
        metadata=metadata,
    )
