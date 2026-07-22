"""Strict opaque cursor codec for persisted anomaly pagination."""

import base64
import binascii
import json
from datetime import datetime
from uuid import UUID

from app.application.queries.anomalies import AnomalyFindingCursor


class InvalidAnomalyFindingCursorError(ValueError):
    """Raised when a public anomaly cursor is malformed."""


def encode_anomaly_finding_cursor(cursor: AnomalyFindingCursor) -> str:
    payload = {
        "created_at": cursor.created_at.isoformat().replace("+00:00", "Z"),
        "id": str(cursor.finding_id),
    }
    raw = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def decode_anomaly_finding_cursor(value: str) -> AnomalyFindingCursor:
    if not isinstance(value, str) or not value:
        raise InvalidAnomalyFindingCursorError("Invalid anomaly pagination cursor.")
    try:
        padding = "=" * (-len(value) % 4)
        raw = base64.b64decode(value + padding, altchars=b"-_", validate=True)
        payload = json.loads(raw.decode("utf-8"))
        if not isinstance(payload, dict) or set(payload) != {"created_at", "id"}:
            raise ValueError
        created_at_value, id_value = payload["created_at"], payload["id"]
        if not isinstance(created_at_value, str) or not isinstance(id_value, str):
            raise ValueError
        if not created_at_value.endswith("Z"):
            raise ValueError
        created_at = datetime.fromisoformat(
            created_at_value.removesuffix("Z") + "+00:00"
        )
        cursor = AnomalyFindingCursor(created_at=created_at, finding_id=UUID(id_value))
        if encode_anomaly_finding_cursor(cursor) != value:
            raise ValueError
        return cursor
    except (
        binascii.Error,
        UnicodeDecodeError,
        json.JSONDecodeError,
        TypeError,
        ValueError,
    ) as error:
        raise InvalidAnomalyFindingCursorError(
            "Invalid anomaly pagination cursor."
        ) from error
