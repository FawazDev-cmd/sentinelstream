"""SQLAlchemy model for normalized log events."""

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import DateTime, Float, Index, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

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
