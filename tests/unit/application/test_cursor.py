import base64
import json
from datetime import UTC, datetime, timedelta, timezone
from uuid import UUID

import pytest

from app.application.queries.cursor import (
    InvalidLogEventCursorError,
    decode_log_event_cursor,
    encode_log_event_cursor,
)
from app.application.queries.logs import LogEventCursor

CURSOR = LogEventCursor(
    datetime(2026, 7, 22, 10, tzinfo=timezone(timedelta(hours=1))),
    UUID("c54b1ea9-a909-4a84-8419-b1f17312e922"),
)


def token(payload: object) -> str:
    return base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")


def test_encoding_is_deterministic_url_safe_canonical_and_round_trips() -> None:
    first = encode_log_event_cursor(CURSOR)
    second = encode_log_event_cursor(CURSOR)
    assert first == second and "=" not in first
    assert set(first) <= set(
        "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_"
    )
    decoded = decode_log_event_cursor(first)
    assert decoded == CURSOR
    assert decoded.timestamp == datetime(2026, 7, 22, 9, tzinfo=UTC)
    payload = json.loads(base64.urlsafe_b64decode(first + "=" * (-len(first) % 4)))
    assert payload == {
        "event_id": str(CURSOR.event_id),
        "timestamp": "2026-07-22T09:00:00Z",
    }
    assert "message" not in payload and "metadata" not in payload


@pytest.mark.parametrize(
    "value",
    [
        "%%%",
        token("not-object"),
        token({}),
        token({"timestamp": "2026-07-22T10:00:00Z"}),
        token({"event_id": str(UUID(int=1))}),
        token({"timestamp": "bad", "event_id": str(UUID(int=1))}),
        token({"timestamp": "2026-07-22T10:00:00", "event_id": str(UUID(int=1))}),
        token({"timestamp": "2026-07-22T10:00:00Z", "event_id": "bad"}),
        token(
            {
                "timestamp": "2026-07-22T10:00:00Z",
                "event_id": str(UUID(int=1)),
                "extra": True,
            }
        ),
    ],
)
def test_invalid_cursor_payloads_are_rejected(value: str) -> None:
    with pytest.raises(InvalidLogEventCursorError, match="Invalid pagination cursor"):
        decode_log_event_cursor(value)


def test_malformed_json_is_rejected() -> None:
    value = base64.urlsafe_b64encode(b"{").decode().rstrip("=")
    with pytest.raises(InvalidLogEventCursorError):
        decode_log_event_cursor(value)
