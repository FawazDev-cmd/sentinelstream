"""Strict opaque incident cursor codec."""

import base64
import binascii
import json
from datetime import datetime
from uuid import UUID

from app.application.queries.incidents import IncidentCursor


class InvalidIncidentCursorError(ValueError):
    """Raised when a public incident cursor is malformed."""


def encode_incident_cursor(cursor: IncidentCursor) -> str:
    payload = {
        "id": str(cursor.incident_id),
        "last_seen_at": cursor.last_seen_at.isoformat().replace("+00:00", "Z"),
    }
    return (
        base64.urlsafe_b64encode(
            json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()
        )
        .decode()
        .rstrip("=")
    )


def decode_incident_cursor(value: str) -> IncidentCursor:
    if not isinstance(value, str) or not value or "=" in value:
        raise InvalidIncidentCursorError("Invalid incident pagination cursor.")
    try:
        raw = base64.b64decode(
            value + "=" * (-len(value) % 4), altchars=b"-_", validate=True
        )
        payload = json.loads(raw.decode())
        if not isinstance(payload, dict) or set(payload) != {"id", "last_seen_at"}:
            raise ValueError
        id_value, timestamp = payload["id"], payload["last_seen_at"]
        if (
            not isinstance(id_value, str)
            or not isinstance(timestamp, str)
            or not timestamp.endswith("Z")
        ):
            raise ValueError
        cursor = IncidentCursor(
            datetime.fromisoformat(timestamp[:-1] + "+00:00"), UUID(id_value)
        )
        if encode_incident_cursor(cursor) != value:
            raise ValueError
        return cursor
    except (
        binascii.Error,
        UnicodeDecodeError,
        json.JSONDecodeError,
        TypeError,
        ValueError,
    ) as error:
        raise InvalidIncidentCursorError(
            "Invalid incident pagination cursor."
        ) from error
