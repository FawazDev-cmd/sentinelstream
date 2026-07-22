"""Normalized log-event domain model and its invariants."""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from types import MappingProxyType
from uuid import UUID

from app.domain.logs.types import LogLevel

SERVICE_MAX_LENGTH = 100
ENVIRONMENT_MAX_LENGTH = 50
MESSAGE_MAX_LENGTH = 4_000
EXCEPTION_TYPE_MAX_LENGTH = 250
EXCEPTION_MESSAGE_MAX_LENGTH = 2_000
TRACE_ID_MAX_LENGTH = 128
REQUEST_ID_MAX_LENGTH = 128
HOST_MAX_LENGTH = 255
METADATA_MAX_TOP_LEVEL_KEYS = 50
METADATA_MAX_KEY_LENGTH = 100
METADATA_MAX_DEPTH = 5

type JsonScalar = str | int | float | bool | None
type JsonValue = JsonScalar | list[JsonValue] | dict[str, JsonValue]
type FrozenJsonValue = (
    JsonScalar | tuple["FrozenJsonValue", ...] | Mapping[str, "FrozenJsonValue"]
)


def _bounded_text(
    value: str,
    *,
    field_name: str,
    maximum: int,
    trim: bool,
) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string")
    normalized = value.strip() if trim else value
    if not normalized.strip():
        raise ValueError(f"{field_name} must not be blank")
    if len(normalized) > maximum:
        raise ValueError(f"{field_name} must be at most {maximum} characters")
    return normalized


def _optional_bounded_text(
    value: str | None, *, field_name: str, maximum: int
) -> str | None:
    if value is None:
        return None
    return _bounded_text(value, field_name=field_name, maximum=maximum, trim=True)


def _utc_datetime(value: datetime, *, field_name: str) -> datetime:
    if not isinstance(value, datetime):
        raise TypeError(f"{field_name} must be a datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
    return value.astimezone(UTC)


def _freeze_metadata(value: object, *, depth: int) -> FrozenJsonValue:
    if depth > METADATA_MAX_DEPTH:
        raise ValueError(
            f"metadata nesting must not exceed {METADATA_MAX_DEPTH} levels"
        )
    if value is None or isinstance(value, (str, bool)):
        return value
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("metadata floats must be finite")
        return value
    if isinstance(value, list):
        return tuple(_freeze_metadata(item, depth=depth + 1) for item in value)
    if isinstance(value, dict):
        frozen: dict[str, FrozenJsonValue] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise TypeError("metadata dictionary keys must be strings")
            if len(key) > METADATA_MAX_KEY_LENGTH:
                raise ValueError(
                    f"metadata key exceeds maximum length of {METADATA_MAX_KEY_LENGTH}"
                )
            frozen[key] = _freeze_metadata(item, depth=depth + 1)
        return MappingProxyType(frozen)
    raise TypeError(f"unsupported metadata value: {type(value).__name__}")


def _freeze_metadata_root(
    metadata: Mapping[str, object],
) -> Mapping[str, FrozenJsonValue]:
    if not isinstance(metadata, dict):
        raise TypeError("metadata must be a dictionary")
    if len(metadata) > METADATA_MAX_TOP_LEVEL_KEYS:
        raise ValueError(
            f"metadata exceeds maximum of {METADATA_MAX_TOP_LEVEL_KEYS} top-level keys"
        )
    frozen = _freeze_metadata(metadata, depth=0)
    if not isinstance(frozen, Mapping):  # pragma: no cover - guaranteed by root check
        raise TypeError("metadata must be a dictionary")
    return frozen


def _thaw_metadata(value: FrozenJsonValue) -> JsonValue:
    if isinstance(value, Mapping):
        return {key: _thaw_metadata(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_thaw_metadata(item) for item in value]
    return value


@dataclass(frozen=True, slots=True)
class LogEvent:
    """A validated normalized log event.

    Fields cannot be reassigned. Metadata is defensively copied and recursively
    frozen; serialized output is a fresh mutable JSON-compatible structure.
    """

    event_id: UUID
    timestamp: datetime
    received_at: datetime
    service: str
    environment: str
    level: LogLevel
    message: str
    exception_type: str | None = None
    exception_message: str | None = None
    latency_ms: float | None = None
    status_code: int | None = None
    trace_id: str | None = None
    request_id: str | None = None
    host: str | None = None
    metadata: Mapping[str, FrozenJsonValue] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.event_id, UUID):
            raise TypeError("event_id must be a UUID")
        if not isinstance(self.level, LogLevel):
            raise TypeError("level must be a LogLevel")

        object.__setattr__(
            self, "timestamp", _utc_datetime(self.timestamp, field_name="timestamp")
        )
        object.__setattr__(
            self,
            "received_at",
            _utc_datetime(self.received_at, field_name="received_at"),
        )
        object.__setattr__(
            self,
            "service",
            _bounded_text(
                self.service,
                field_name="service",
                maximum=SERVICE_MAX_LENGTH,
                trim=True,
            ),
        )
        object.__setattr__(
            self,
            "environment",
            _bounded_text(
                self.environment,
                field_name="environment",
                maximum=ENVIRONMENT_MAX_LENGTH,
                trim=True,
            ),
        )
        object.__setattr__(
            self,
            "message",
            _bounded_text(
                self.message,
                field_name="message",
                maximum=MESSAGE_MAX_LENGTH,
                trim=False,
            ),
        )
        for name, maximum in (
            ("exception_type", EXCEPTION_TYPE_MAX_LENGTH),
            ("exception_message", EXCEPTION_MESSAGE_MAX_LENGTH),
            ("trace_id", TRACE_ID_MAX_LENGTH),
            ("request_id", REQUEST_ID_MAX_LENGTH),
            ("host", HOST_MAX_LENGTH),
        ):
            object.__setattr__(
                self,
                name,
                _optional_bounded_text(
                    getattr(self, name), field_name=name, maximum=maximum
                ),
            )

        if self.latency_ms is not None:
            if isinstance(self.latency_ms, bool) or not isinstance(
                self.latency_ms, (int, float)
            ):
                raise TypeError("latency_ms must be a number")
            if not math.isfinite(self.latency_ms) or self.latency_ms < 0:
                raise ValueError("latency_ms must be finite and non-negative")
            object.__setattr__(self, "latency_ms", float(self.latency_ms))

        if self.status_code is not None:
            if isinstance(self.status_code, bool) or not isinstance(
                self.status_code, int
            ):
                raise TypeError("status_code must be an integer")
            if not 100 <= self.status_code <= 599:
                raise ValueError("status_code must be between 100 and 599")

        # The public annotation is a Mapping because construction replaces the
        # accepted dictionary with an immutable mapping proxy.
        object.__setattr__(self, "metadata", _freeze_metadata_root(self.metadata))

    def to_dict(self) -> dict[str, object]:
        """Return a deterministic, JSON-encodable representation."""
        return {
            "event_id": str(self.event_id),
            "timestamp": self.timestamp.isoformat(),
            "received_at": self.received_at.isoformat(),
            "service": self.service,
            "environment": self.environment,
            "level": self.level.value,
            "message": self.message,
            "exception_type": self.exception_type,
            "exception_message": self.exception_message,
            "latency_ms": self.latency_ms,
            "status_code": self.status_code,
            "trace_id": self.trace_id,
            "request_id": self.request_id,
            "host": self.host,
            "metadata": _thaw_metadata(self.metadata),
        }
