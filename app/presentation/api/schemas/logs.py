"""Schemas for the external log-ingestion boundary."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictFloat,
    StrictInt,
    StrictStr,
    field_validator,
)

from app.application.services.ingestion import IngestionInput
from app.domain.logs.models import (
    ENVIRONMENT_MAX_LENGTH,
    EXCEPTION_MESSAGE_MAX_LENGTH,
    EXCEPTION_TYPE_MAX_LENGTH,
    HOST_MAX_LENGTH,
    MESSAGE_MAX_LENGTH,
    REQUEST_ID_MAX_LENGTH,
    SERVICE_MAX_LENGTH,
    TRACE_ID_MAX_LENGTH,
    JsonValue,
)


class LogIngestionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    timestamp: datetime
    service: StrictStr = Field(min_length=1, max_length=SERVICE_MAX_LENGTH)
    environment: StrictStr = Field(min_length=1, max_length=ENVIRONMENT_MAX_LENGTH)
    level: StrictStr = Field(min_length=1, max_length=20)
    message: StrictStr = Field(min_length=1, max_length=MESSAGE_MAX_LENGTH)
    event_id: UUID | None = None
    exception_type: StrictStr | None = Field(
        None, min_length=1, max_length=EXCEPTION_TYPE_MAX_LENGTH
    )
    exception_message: StrictStr | None = Field(
        None, min_length=1, max_length=EXCEPTION_MESSAGE_MAX_LENGTH
    )
    latency_ms: StrictFloat | StrictInt | None = Field(None, ge=0)
    status_code: StrictInt | None = Field(None, ge=100, le=599)
    trace_id: StrictStr | None = Field(
        None, min_length=1, max_length=TRACE_ID_MAX_LENGTH
    )
    request_id: StrictStr | None = Field(
        None, min_length=1, max_length=REQUEST_ID_MAX_LENGTH
    )
    host: StrictStr | None = Field(None, min_length=1, max_length=HOST_MAX_LENGTH)
    metadata: dict[str, JsonValue] = Field(default_factory=dict)

    @field_validator("timestamp")
    @classmethod
    def timestamp_must_be_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("timestamp must be timezone-aware")
        return value

    def to_input(self) -> IngestionInput:
        return IngestionInput(**self.model_dump())


class LogIngestionResponse(BaseModel):
    status: Literal["accepted"] = "accepted"
    event_id: UUID
