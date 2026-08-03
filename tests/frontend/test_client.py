"""Focused tests for the Streamlit REST boundary; no UI browser automation."""

from __future__ import annotations

from unittest.mock import Mock

import pytest
import requests

from streamlit_app.client import ApiError, SentinelStreamClient


def response(status: int, body: object = None, *, malformed: bool = False) -> Mock:
    value = Mock(spec=requests.Response)
    value.ok = 200 <= status < 400
    value.status_code = status
    if malformed:
        value.json.side_effect = ValueError("invalid JSON")
    else:
        value.json.return_value = body
    return value


def test_uses_configured_base_url_timeout_and_query() -> None:
    session = Mock(spec=requests.Session)
    session.request.return_value = response(200, {"status": "ok"})
    client = SentinelStreamClient("http://backend:8000/", session=session)

    assert client.health() == {"status": "ok"}
    session.request.assert_called_once_with(
        "GET",
        "http://backend:8000/health",
        params=None,
        json=None,
        timeout=5.0,
    )


def test_timeout_is_sanitized() -> None:
    session = Mock(spec=requests.Session)
    session.request.side_effect = requests.Timeout("secret payload")
    client = SentinelStreamClient("http://backend", session=session)

    with pytest.raises(ApiError, match="timed out") as captured:
        client.health()

    assert "secret payload" not in str(captured.value)


def test_network_failure_is_sanitized() -> None:
    session = Mock(spec=requests.Session)
    session.request.side_effect = requests.ConnectionError("postgresql://secret")
    client = SentinelStreamClient("http://backend", session=session)

    with pytest.raises(ApiError, match="unavailable") as captured:
        client.health()

    assert "postgresql" not in str(captured.value)


def test_api_detail_is_used_without_stack_trace() -> None:
    session = Mock(spec=requests.Session)
    session.request.return_value = response(422, {"detail": "Invalid filter."})
    client = SentinelStreamClient("http://backend", session=session)

    with pytest.raises(ApiError, match="Invalid filter"):
        client.list_logs()


def test_malformed_json_and_page_are_rejected() -> None:
    session = Mock(spec=requests.Session)
    session.request.side_effect = [
        response(200, malformed=True),
        response(200, {"items": "wrong", "next_cursor": None}),
    ]
    client = SentinelStreamClient("http://backend", session=session)

    with pytest.raises(ApiError, match="malformed response"):
        client.health()
    with pytest.raises(ApiError, match="malformed paginated"):
        client.list_logs()


def test_count_all_follows_cursor_without_omissions() -> None:
    session = Mock(spec=requests.Session)
    session.request.side_effect = [
        response(200, {"items": [{"id": "1"}, {"id": "2"}], "next_cursor": "next"}),
        response(200, {"items": [{"id": "3"}], "next_cursor": None}),
    ]
    client = SentinelStreamClient("http://backend", session=session)

    assert client.count_all("/api/v1/logs") == 3
    second_call = session.request.call_args_list[1]
    assert second_call.kwargs["params"] == {"limit": 100, "cursor": "next"}


def test_ingestion_posts_existing_contract() -> None:
    session = Mock(spec=requests.Session)
    session.request.return_value = response(
        202, {"status": "accepted", "event_id": "event-id"}
    )
    client = SentinelStreamClient("http://backend", session=session)
    payload = {"service": "payments", "message": "safe"}

    assert client.ingest_log(payload)["status"] == "accepted"
    assert session.request.call_args.kwargs["json"] == payload
