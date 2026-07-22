"""SQLAlchemy models for normalized log events and anomaly findings."""

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.domain.anomalies.models import RULE_ID_MAX_LENGTH, TITLE_MAX_LENGTH
from app.domain.logs.models import (
    ENVIRONMENT_MAX_LENGTH,
    EXCEPTION_MESSAGE_MAX_LENGTH,
    EXCEPTION_TYPE_MAX_LENGTH,
    HOST_MAX_LENGTH,
    MESSAGE_MAX_LENGTH,
    REQUEST_ID_MAX_LENGTH,
    SERVICE_MAX_LENGTH,
    TRACE_ID_MAX_LENGTH,
)
from app.infrastructure.database.base import Base

ANOMALY_TYPE_MAX_LENGTH = 50
ANOMALY_SEVERITY_MAX_LENGTH = 20


class LogEventRecord(Base):
    __tablename__ = "log_events"
    __table_args__ = (
        Index("ix_log_events_timestamp", "timestamp"),
        Index("ix_log_events_received_at", "received_at"),
        Index("ix_log_events_service", "service"),
        Index("ix_log_events_environment", "environment"),
        Index("ix_log_events_level", "level"),
        Index("ix_log_events_service_timestamp", "service", "timestamp"),
    )

    event_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    service: Mapped[str] = mapped_column(String(SERVICE_MAX_LENGTH), nullable=False)
    environment: Mapped[str] = mapped_column(
        String(ENVIRONMENT_MAX_LENGTH), nullable=False
    )
    level: Mapped[str] = mapped_column(String(8), nullable=False)
    message: Mapped[str] = mapped_column(String(MESSAGE_MAX_LENGTH), nullable=False)
    exception_type: Mapped[str | None] = mapped_column(
        String(EXCEPTION_TYPE_MAX_LENGTH), nullable=True
    )
    exception_message: Mapped[str | None] = mapped_column(
        String(EXCEPTION_MESSAGE_MAX_LENGTH), nullable=True
    )
    latency_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    status_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    trace_id: Mapped[str | None] = mapped_column(
        String(TRACE_ID_MAX_LENGTH), nullable=True
    )
    request_id: Mapped[str | None] = mapped_column(
        String(REQUEST_ID_MAX_LENGTH), nullable=True
    )
    host: Mapped[str | None] = mapped_column(String(HOST_MAX_LENGTH), nullable=True)
    event_metadata: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONB, nullable=False
    )


class AnomalyFindingRecord(Base):
    __tablename__ = "anomaly_findings"
    __table_args__ = (
        UniqueConstraint("event_id", "rule_id", name="uq_anomaly_findings_event_rule"),
        Index("ix_anomaly_findings_event_id", "event_id"),
        Index("ix_anomaly_findings_severity", "severity"),
        Index("ix_anomaly_findings_anomaly_type", "anomaly_type"),
        Index("ix_anomaly_findings_created_at", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    event_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("log_events.event_id", ondelete="CASCADE"),
        nullable=False,
    )
    anomaly_type: Mapped[str] = mapped_column(
        String(ANOMALY_TYPE_MAX_LENGTH), nullable=False
    )
    severity: Mapped[str] = mapped_column(
        String(ANOMALY_SEVERITY_MAX_LENGTH), nullable=False
    )
    rule_id: Mapped[str] = mapped_column(String(RULE_ID_MAX_LENGTH), nullable=False)
    title: Mapped[str] = mapped_column(String(TITLE_MAX_LENGTH), nullable=False)
    evidence: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )


class IncidentRecord(Base):
    __tablename__ = "incidents"
    __table_args__ = (
        CheckConstraint("finding_count >= 2", name="ck_incidents_finding_count"),
        CheckConstraint(
            "started_at <= last_seen_at", name="ck_incidents_occurrence_range"
        ),
        Index("ix_incidents_started_at", "started_at"),
        Index("ix_incidents_last_seen_at", "last_seen_at"),
        Index("ix_incidents_highest_severity", "highest_severity"),
        Index("ix_incidents_service", "service"),
        Index("ix_incidents_environment", "environment"),
        Index("ix_incidents_anomaly_type", "anomaly_type"),
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    service: Mapped[str] = mapped_column(String(SERVICE_MAX_LENGTH), nullable=False)
    environment: Mapped[str] = mapped_column(
        String(ENVIRONMENT_MAX_LENGTH), nullable=False
    )
    anomaly_type: Mapped[str] = mapped_column(
        String(ANOMALY_TYPE_MAX_LENGTH), nullable=False
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    finding_count: Mapped[int] = mapped_column(Integer, nullable=False)
    highest_severity: Mapped[str] = mapped_column(
        String(ANOMALY_SEVERITY_MAX_LENGTH), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )


class IncidentFindingRecord(Base):
    __tablename__ = "incident_findings"
    __table_args__ = (
        UniqueConstraint(
            "incident_id", "position", name="uq_incident_findings_incident_position"
        ),
        UniqueConstraint("finding_id", name="uq_incident_findings_finding"),
        CheckConstraint("position >= 0", name="ck_incident_findings_position"),
    )

    incident_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("incidents.id", ondelete="CASCADE"),
        primary_key=True,
    )
    finding_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("anomaly_findings.id", ondelete="RESTRICT"),
        primary_key=True,
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
