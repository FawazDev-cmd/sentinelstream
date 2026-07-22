"""Opaque cursor encoding for persisted-log pagination."""

import base64
import binascii
import json
from datetime import datetime
from uuid import UUID

from app.application.queries.logs import LogEventCursor


class InvalidLogEventCursorError(ValueError):
    """Raised when a public pagination cursor is malformed."""


def encode_log_event_cursor(cursor: LogEventCursor) -> str:
    payload = {
        "event_id": str(cursor.event_id),
        "timestamp": cursor.timestamp.isoformat().replace("+00:00", "Z"),
    }
    serialized = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()
    return base64.urlsafe_b64encode(serialized).decode().rstrip("=")


def decode_log_event_cursor(value: str) -> LogEventCursor:
    if not isinstance(value, str) or not value:
        raise InvalidLogEventCursorError("Invalid pagination cursor.")
    try:
        padding = "=" * (-len(value) % 4)
        raw = base64.b64decode(value + padding, altchars=b"-_", validate=True)
        payload = json.loads(raw.decode("utf-8"))
        if not isinstance(payload, dict) or set(payload) != {"timestamp", "event_id"}:
            raise ValueError
        timestamp_value = payload["timestamp"]
        event_id_value = payload["event_id"]
        if not isinstance(timestamp_value, str) or not isinstance(event_id_value, str):
            raise ValueError
        timestamp = datetime.fromisoformat(timestamp_value.replace("Z", "+00:00"))
        return LogEventCursor(timestamp=timestamp, event_id=UUID(event_id_value))
    except (
        binascii.Error,
        UnicodeDecodeError,
        json.JSONDecodeError,
        TypeError,
        ValueError,
    ) as error:
        raise InvalidLogEventCursorError("Invalid pagination cursor.") from error
