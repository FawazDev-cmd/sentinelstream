"""Seed SentinelStream through its public REST API for deterministic screenshots."""

from __future__ import annotations

import argparse
import os
import sys
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Final

import requests

DEFAULT_BACKEND_URL: Final = "http://127.0.0.1:8000"
DEFAULT_WAIT_SECONDS: Final = 15.0
REQUEST_TIMEOUT: Final = (3.05, 15.0)

JsonValue = None | bool | int | float | str | list["JsonValue"] | dict[str, "JsonValue"]
JsonObject = dict[str, JsonValue]


@dataclass(frozen=True, slots=True)
class DemoEvent:
    """A named, deterministic public ingestion payload."""

    label: str
    payload: JsonObject


def demo_events() -> tuple[DemoEvent, ...]:
    """Return stable events in source-event chronological order."""

    return (
        DemoEvent(
            "gateway healthy request",
            {
                "event_id": "d1800000-0000-4000-8000-000000000001",
                "timestamp": "2026-08-04T08:00:00Z",
                "service": "gateway",
                "environment": "production",
                "level": "INFO",
                "message": "Request routing completed normally",
                "metadata": {"demo": True, "region": "eu-west"},
            },
        ),
        DemoEvent(
            "payments elevated queue depth",
            {
                "event_id": "d1800000-0000-4000-8000-000000000002",
                "timestamp": "2026-08-04T08:01:00Z",
                "service": "payments-api",
                "environment": "production",
                "level": "WARNING",
                "message": "Payment queue depth is elevated but within limits",
                "metadata": {"demo": True, "queue_depth": 42},
            },
        ),
        DemoEvent(
            "payments provider error one",
            {
                "event_id": "d1800000-0000-4000-8000-000000000003",
                "timestamp": "2026-08-04T08:05:00Z",
                "service": "payments-api",
                "environment": "production",
                "level": "ERROR",
                "message": "Payment provider request failed",
                "metadata": {"demo": True, "provider": "fictional-pay"},
            },
        ),
        DemoEvent(
            "payments provider error two",
            {
                "event_id": "d1800000-0000-4000-8000-000000000004",
                "timestamp": "2026-08-04T08:07:00Z",
                "service": "payments-api",
                "environment": "production",
                "level": "CRITICAL",
                "message": "Payment provider circuit opened",
                "metadata": {"demo": True, "provider": "fictional-pay"},
            },
        ),
        DemoEvent(
            "payments provider error three",
            {
                "event_id": "d1800000-0000-4000-8000-000000000005",
                "timestamp": "2026-08-04T08:09:00Z",
                "service": "payments-api",
                "environment": "production",
                "level": "ERROR",
                "message": "Payment provider request failed after circuit recovery",
                "metadata": {"demo": True, "provider": "fictional-pay"},
            },
        ),
        DemoEvent(
            "auth elevated latency",
            {
                "event_id": "d1800000-0000-4000-8000-000000000006",
                "timestamp": "2026-08-04T08:15:00Z",
                "service": "auth-service",
                "environment": "production",
                "level": "WARNING",
                "message": "Authentication request completed slowly",
                "metadata": {"demo": True, "flow": "token-refresh"},
                "latency_ms": 1500,
            },
        ),
        DemoEvent(
            "auth critical latency",
            {
                "event_id": "d1800000-0000-4000-8000-000000000007",
                "timestamp": "2026-08-04T08:17:00Z",
                "service": "auth-service",
                "environment": "production",
                "level": "INFO",
                "message": "Authentication request exceeded latency objective",
                "metadata": {"demo": True, "flow": "token-refresh"},
                "latency_ms": 6500,
            },
        ),
        DemoEvent(
            "gateway upstream exception",
            {
                "event_id": "d1800000-0000-4000-8000-000000000008",
                "timestamp": "2026-08-04T08:25:00Z",
                "service": "gateway",
                "environment": "production",
                "level": "ERROR",
                "message": "Upstream request failed",
                "metadata": {"demo": True, "route": "/checkout"},
                "status_code": 503,
                "exception_type": "UpstreamUnavailable",
            },
        ),
        DemoEvent(
            "gateway critical upstream exception",
            {
                "event_id": "d1800000-0000-4000-8000-000000000009",
                "timestamp": "2026-08-04T08:27:00Z",
                "service": "gateway",
                "environment": "production",
                "level": "CRITICAL",
                "message": "Upstream request failed across all routes",
                "metadata": {"demo": True, "route": "/checkout"},
                "status_code": 560,
                "exception_type": "UpstreamUnavailable",
            },
        ),
    )


def resolve_backend_url(
    cli_value: str | None,
    environment: Mapping[str, str] | None = None,
) -> str:
    """Resolve the CLI override, environment setting, or local default."""

    values = os.environ if environment is None else environment
    selected = (
        cli_value or values.get("SENTINELSTREAM_BACKEND_URL") or DEFAULT_BACKEND_URL
    )
    resolved = selected.strip().rstrip("/")
    if not resolved:
        raise ValueError("backend URL cannot be empty")
    return resolved


class RestApi:
    """Small client limited to SentinelStream's public HTTP surface."""

    def __init__(
        self, backend_url: str, session: requests.Session | None = None
    ) -> None:
        self._backend_url = backend_url
        self._session = session or requests.Session()

    def get_object(self, path: str) -> JsonObject:
        response = self._session.get(
            f"{self._backend_url}{path}", timeout=REQUEST_TIMEOUT
        )
        response.raise_for_status()
        return _object_response(response)

    def submit(self, payload: JsonObject) -> JsonObject:
        response = self._session.post(
            f"{self._backend_url}/api/v1/logs",
            json=payload,
            timeout=REQUEST_TIMEOUT,
        )
        response.raise_for_status()
        if response.status_code != 202:
            raise RuntimeError(
                f"expected HTTP 202, received HTTP {response.status_code}"
            )
        return _object_response(response)

    def list_all(self, path: str) -> list[JsonObject]:
        items: list[JsonObject] = []
        cursor: str | None = None
        while True:
            params: dict[str, str | int] = {"limit": 100}
            if cursor is not None:
                params["cursor"] = cursor
            response = self._session.get(
                f"{self._backend_url}{path}",
                params=params,
                timeout=REQUEST_TIMEOUT,
            )
            response.raise_for_status()
            page = _object_response(response)
            raw_items = page.get("items")
            if not isinstance(raw_items, list):
                raise RuntimeError(f"{path} returned an invalid items collection")
            for item in raw_items:
                if not isinstance(item, dict):
                    raise RuntimeError(f"{path} returned a non-object item")
                items.append(item)
            raw_cursor = page.get("next_cursor")
            if raw_cursor is None:
                return items
            if not isinstance(raw_cursor, str):
                raise RuntimeError(f"{path} returned an invalid cursor")
            cursor = raw_cursor


def _object_response(response: requests.Response) -> JsonObject:
    raw: object = response.json()
    if not isinstance(raw, dict):
        raise RuntimeError("API returned a non-object JSON response")
    return raw


def _required_string(value: JsonObject, key: str) -> str:
    raw = value.get(key)
    if not isinstance(raw, str):
        raise RuntimeError(f"API object is missing string field {key!r}")
    return raw


def _contains_forbidden_incident_field(value: JsonValue) -> bool:
    if isinstance(value, dict):
        if "message" in value or "metadata" in value:
            return True
        return any(_contains_forbidden_incident_field(item) for item in value.values())
    if isinstance(value, list):
        return any(_contains_forbidden_incident_field(item) for item in value)
    return False


def _verify_visible_data(api: RestApi, events: Sequence[DemoEvent]) -> None:
    logs = api.list_all("/api/v1/logs")
    anomalies = api.list_all("/api/v1/anomalies")
    incidents = api.list_all("/api/v1/incidents")
    event_ids = {_required_string(event.payload, "event_id") for event in events}

    visible_logs = [item for item in logs if item.get("event_id") in event_ids]
    visible_anomalies = [
        item for item in anomalies if item.get("event_id") in event_ids
    ]
    services = {"payments-api", "auth-service", "gateway"}
    visible_incidents = [
        item
        for item in incidents
        if item.get("service") in services and item.get("environment") == "production"
    ]

    if len(visible_logs) != len(events):
        raise RuntimeError(
            f"only {len(visible_logs)} of {len(events)} demo logs are visible; "
            "increase --wait-seconds if the worker is still processing"
        )

    anomaly_types = {
        _required_string(item, "anomaly_type") for item in visible_anomalies
    }
    severities = {_required_string(item, "severity") for item in visible_anomalies}
    expected_types = {
        "error_level",
        "server_error_status",
        "exception_present",
        "high_latency",
    }
    if not expected_types.issubset(anomaly_types):
        raise RuntimeError(
            f"missing anomaly types: {sorted(expected_types - anomaly_types)}"
        )
    if not {"medium", "high", "critical"}.issubset(severities):
        raise RuntimeError("the visible anomaly data does not contain mixed severities")
    if len(visible_incidents) < 2:
        raise RuntimeError(
            f"expected at least two incidents, found {len(visible_incidents)}"
        )

    details: list[JsonObject] = []
    for incident in visible_incidents:
        incident_id = _required_string(incident, "id")
        detail = api.get_object(f"/api/v1/incidents/{incident_id}")
        findings = detail.get("findings")
        if not isinstance(findings, list) or len(findings) < 2:
            raise RuntimeError(f"incident {incident_id} has fewer than two findings")
        positions = [
            finding.get("position") for finding in findings if isinstance(finding, dict)
        ]
        if positions != list(range(len(findings))):
            raise RuntimeError(f"incident {incident_id} findings are not ordered")
        if _contains_forbidden_incident_field(detail):
            raise RuntimeError(
                f"incident {incident_id} exposes a source message or metadata"
            )
        details.append(detail)

    qualifying_pairs = {
        (detail.get("service"), detail.get("anomaly_type")) for detail in details
    }
    required_pairs = {
        ("payments-api", "error_level"),
        ("auth-service", "high_latency"),
    }
    if not required_pairs.issubset(qualifying_pairs):
        raise RuntimeError(
            "expected payments and authentication incidents are not visible"
        )

    incident_ids = [_required_string(item, "id") for item in visible_incidents]
    print(f"Visible demo logs: {len(visible_logs)}")
    print(f"Visible demo anomaly findings: {len(visible_anomalies)}")
    print(f"Visible production incidents for demo services: {len(visible_incidents)}")
    print(f"Visible anomaly types: {', '.join(sorted(anomaly_types))}")
    print(f"Visible anomaly severities: {', '.join(sorted(severities))}")
    print("Current visible incident IDs:")
    for incident_id in incident_ids:
        print(f"  - {incident_id}")
    print("Incident detail findings are ordered and omit source messages and metadata.")
    print(
        "Note: the eager grouping runtime persists the first qualifying two-finding "
        "payments incident; the third matching finding remains unassigned by design."
    )


def _parse_args(arguments: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Seed deterministic screenshot data through SentinelStream's REST API."
        )
    )
    parser.add_argument(
        "--backend-url",
        help="API base URL (overrides SENTINELSTREAM_BACKEND_URL)",
    )
    parser.add_argument(
        "--wait-seconds",
        type=float,
        default=DEFAULT_WAIT_SECONDS,
        help="seconds to wait before verifying asynchronous processing",
    )
    return parser.parse_args(arguments)


def main(arguments: Sequence[str] | None = None) -> int:
    args = _parse_args(arguments)
    if args.wait_seconds < 0:
        print("--wait-seconds must be non-negative", file=sys.stderr)
        return 2

    try:
        backend_url = resolve_backend_url(args.backend_url)
        api = RestApi(backend_url)
        health = api.get_object("/health")
        print(f"Backend: {backend_url}")
        print(f"Backend health: {health}")

        events = demo_events()
        accepted = 0
        failures: list[str] = []
        for event in events:
            try:
                api.submit(event.payload)
                accepted += 1
                print(f"Accepted: {event.label}")
            except requests.RequestException as error:
                failures.append(f"{event.label}: {type(error).__name__}")
                print(
                    f"Failed: {event.label} ({type(error).__name__})", file=sys.stderr
                )
            except RuntimeError as error:
                failures.append(f"{event.label}: {error}")
                print(f"Failed: {event.label} ({error})", file=sys.stderr)

        print(f"Logs submitted: {len(events)}")
        print(f"Accepted submissions: {accepted}")
        print(f"Failed submissions: {len(failures)}")
        print("Processing is asynchronous after HTTP 202 queue acceptance.")
        print(f"Suggested wait time: {args.wait_seconds:g} seconds")
        if failures:
            return 1

        if args.wait_seconds:
            time.sleep(args.wait_seconds)
        _verify_visible_data(api, events)
    except (requests.RequestException, RuntimeError, ValueError) as error:
        print(f"Seed verification failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
