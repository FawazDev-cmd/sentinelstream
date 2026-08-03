"""Small, defensive REST client used only by the Streamlit presentation layer."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import requests

JsonObject = dict[str, Any]


class ApiError(Exception):
    """A safe, user-displayable backend communication failure."""


class SentinelStreamClient:
    """Call SentinelStream exclusively through its public HTTP API."""

    def __init__(
        self,
        base_url: str,
        *,
        timeout_seconds: float = 5.0,
        session: requests.Session | None = None,
    ) -> None:
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self._session = session or requests.Session()

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: Mapping[str, Any] | None = None,
        json: Mapping[str, Any] | None = None,
    ) -> JsonObject:
        try:
            response = self._session.request(
                method,
                f"{self.base_url}{path}",
                params=dict(params) if params is not None else None,
                json=dict(json) if json is not None else None,
                timeout=self.timeout_seconds,
            )
        except requests.Timeout as error:
            raise ApiError("The backend request timed out. Try again.") from error
        except requests.RequestException as error:
            raise ApiError(
                "The backend is unavailable. Check that the API is running."
            ) from error

        if not response.ok:
            message = f"The backend returned HTTP {response.status_code}."
            try:
                body = response.json()
                detail = body.get("detail") if isinstance(body, dict) else None
                if isinstance(detail, str) and detail:
                    message = detail
            except (requests.RequestException, ValueError):
                pass
            raise ApiError(message)

        try:
            body = response.json()
        except (requests.RequestException, ValueError) as error:
            raise ApiError("The backend returned a malformed response.") from error
        if not isinstance(body, dict):
            raise ApiError("The backend returned a malformed response.")
        return body

    def health(self) -> JsonObject:
        return self._request("GET", "/health")

    def list_logs(self, params: Mapping[str, Any] | None = None) -> JsonObject:
        return self._page("/api/v1/logs", params)

    def list_anomalies(self, params: Mapping[str, Any] | None = None) -> JsonObject:
        return self._page("/api/v1/anomalies", params)

    def list_incidents(self, params: Mapping[str, Any] | None = None) -> JsonObject:
        return self._page("/api/v1/incidents", params)

    def get_incident(self, incident_id: str) -> JsonObject:
        return self._request("GET", f"/api/v1/incidents/{incident_id}")

    def ingest_log(self, payload: Mapping[str, Any]) -> JsonObject:
        return self._request("POST", "/api/v1/logs", json=payload)

    def count_all(self, path: str, *, page_size: int = 100) -> int:
        """Count a demo dataset through the API's existing cursor contract."""
        cursor: str | None = None
        seen: set[str] = set()
        total = 0
        while True:
            params: dict[str, object] = {"limit": page_size}
            if cursor is not None:
                params["cursor"] = cursor
            page = self._page(path, params)
            total += len(page["items"])
            cursor = page["next_cursor"]
            if cursor is None:
                return total
            if cursor in seen:
                raise ApiError("The backend returned a repeated pagination cursor.")
            seen.add(cursor)

    def log_lookup(self) -> dict[str, JsonObject]:
        """Build safe anomaly display context from the public logs API."""
        lookup: dict[str, JsonObject] = {}
        cursor: str | None = None
        seen: set[str] = set()
        while True:
            params: dict[str, object] = {"limit": 100}
            if cursor is not None:
                params["cursor"] = cursor
            page = self.list_logs(params)
            for item in page["items"]:
                event_id = item.get("event_id")
                if isinstance(event_id, str):
                    lookup[event_id] = item
            cursor = page["next_cursor"]
            if cursor is None:
                return lookup
            if cursor in seen:
                raise ApiError("The backend returned a repeated pagination cursor.")
            seen.add(cursor)

    def _page(self, path: str, params: Mapping[str, Any] | None = None) -> JsonObject:
        body = self._request("GET", path, params=params)
        items = body.get("items")
        cursor = body.get("next_cursor")
        if not isinstance(items, list) or not all(
            isinstance(item, dict) for item in items
        ):
            raise ApiError("The backend returned a malformed paginated response.")
        if cursor is not None and not isinstance(cursor, str):
            raise ApiError("The backend returned a malformed paginated response.")
        return {"items": items, "next_cursor": cursor}
