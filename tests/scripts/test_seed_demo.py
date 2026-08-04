from __future__ import annotations

import ast
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

import pytest

from app.presentation.api.schemas.logs import LogIngestionRequest
from scripts.seed_demo import DEFAULT_BACKEND_URL, demo_events, resolve_backend_url


def test_demo_payloads_are_valid_and_deterministic() -> None:
    events = demo_events()

    assert len(events) == 9
    assert len({event.label for event in events}) == len(events)
    assert len({event.payload["event_id"] for event in events}) == len(events)

    for event in events:
        LogIngestionRequest.model_validate(event.payload)
        UUID(str(event.payload["event_id"]))


def test_demo_timestamps_are_explicit_utc_and_chronological() -> None:
    timestamps = [
        datetime.fromisoformat(str(event.payload["timestamp"]).replace("Z", "+00:00"))
        for event in demo_events()
    ]

    assert timestamps == sorted(timestamps)
    assert all(timestamp.tzinfo == UTC for timestamp in timestamps)


def test_demo_dataset_contains_normal_and_anomalous_scenarios() -> None:
    payloads = [event.payload for event in demo_events()]

    assert {payload["service"] for payload in payloads} == {
        "payments-api",
        "auth-service",
        "gateway",
    }
    assert {payload["environment"] for payload in payloads} == {"production"}
    assert {"INFO", "WARNING"}.issubset({payload["level"] for payload in payloads})
    assert any(payload.get("level") in {"ERROR", "CRITICAL"} for payload in payloads)
    assert any("status_code" in payload for payload in payloads)
    assert any("exception_type" in payload for payload in payloads)
    assert any("latency_ms" in payload for payload in payloads)


def test_backend_url_configuration_precedence() -> None:
    assert resolve_backend_url(None, {}) == DEFAULT_BACKEND_URL
    assert (
        resolve_backend_url(None, {"SENTINELSTREAM_BACKEND_URL": "http://api:8000/"})
        == "http://api:8000"
    )
    assert (
        resolve_backend_url(
            "http://localhost:9000/",
            {"SENTINELSTREAM_BACKEND_URL": "http://api:8000"},
        )
        == "http://localhost:9000"
    )


def test_blank_backend_url_is_rejected() -> None:
    with pytest.raises(ValueError, match="cannot be empty"):
        resolve_backend_url("   ", {})


def test_seed_script_has_rest_only_imports() -> None:
    script = Path(__file__).parents[2] / "scripts" / "seed_demo.py"
    tree = ast.parse(script.read_text(encoding="utf-8-sig"))
    imported_roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported_roots.update(
                alias.name.split(".", maxsplit=1)[0] for alias in node.names
            )
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported_roots.add(node.module.split(".", maxsplit=1)[0])

    forbidden = {"app", "asyncpg", "sqlalchemy", "streamlit_app"}
    assert imported_roots.isdisjoint(forbidden)
    assert "requests" in imported_roots
