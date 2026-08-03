"""Streamlit demonstration UI for SentinelStream's existing REST API."""

from __future__ import annotations

import os
from datetime import UTC, datetime
from typing import Any

import streamlit as st

from streamlit_app.client import ApiError, SentinelStreamClient

BACKEND_URL = os.getenv("STREAMLIT_BACKEND_URL", "http://127.0.0.1:8000")
PAGE_SIZE = 25
PAGES = ("Overview", "Logs", "Anomalies", "Incidents", "Demo", "About")


def client() -> SentinelStreamClient:
    return SentinelStreamClient(BACKEND_URL)


def nonempty_params(**values: object) -> dict[str, object]:
    return {key: value for key, value in values.items() if value not in (None, "")}


def reset_cursor(name: str) -> None:
    st.session_state[f"{name}_cursors"] = [None]
    st.session_state[f"{name}_index"] = 0


def paged_request(name: str, fetch: Any, filters: dict[str, object]) -> dict[str, Any]:
    signature = tuple(sorted(filters.items()))
    if st.session_state.get(f"{name}_signature") != signature:
        st.session_state[f"{name}_signature"] = signature
        reset_cursor(name)
    cursors = st.session_state.setdefault(f"{name}_cursors", [None])
    index = st.session_state.setdefault(f"{name}_index", 0)
    params = {**filters, "limit": PAGE_SIZE}
    cursor = cursors[index]
    if cursor:
        params["cursor"] = cursor
    page = fetch(params)
    previous, _, following = st.columns([1, 3, 1])
    if previous.button("Previous", disabled=index == 0, key=f"{name}_previous"):
        st.session_state[f"{name}_index"] = index - 1
        st.rerun()
    if following.button(
        "Next", disabled=page["next_cursor"] is None, key=f"{name}_next"
    ):
        next_cursor = page["next_cursor"]
        if len(cursors) == index + 1:
            cursors.append(next_cursor)
        else:
            cursors[index + 1] = next_cursor
        st.session_state[f"{name}_index"] = index + 1
        st.rerun()
    st.caption(f"Page {index + 1} · up to {PAGE_SIZE} rows · server-side cursor")
    return page


def show_error(error: ApiError) -> None:
    st.error(str(error))


def overview(api: SentinelStreamClient) -> None:
    st.title("SentinelStream")
    st.write(
        "Deterministic log intelligence: ingest structured events, detect anomalies, "
        "and group related findings into persisted incidents."
    )
    try:
        health = api.health()
        st.success(
            f"Backend {health.get('status', 'unknown')} · "
            f"{health.get('service', 'API')}"
        )
        st.caption(
            "API process health is available. Database connectivity is "
            "exercised by the three read APIs below; the current health "
            "contract has no separate DB field."
        )
        if st.button("Refresh overview") or "overview_counts" not in st.session_state:
            st.session_state["overview_counts"] = (
                api.count_all("/api/v1/logs"),
                api.count_all("/api/v1/anomalies"),
                api.count_all("/api/v1/incidents"),
            )
        logs, anomalies, incidents = st.session_state["overview_counts"]
        columns = st.columns(3)
        columns[0].metric("Total logs", logs)
        columns[1].metric("Total anomalies", anomalies)
        columns[2].metric("Total incidents", incidents)
        st.success("Database-backed API reads completed successfully.")
    except ApiError as error:
        show_error(error)


def logs_page(api: SentinelStreamClient) -> None:
    st.header("Logs")
    a, b, c = st.columns(3)
    service = a.text_input("Service")
    environment = b.text_input("Environment")
    level = c.selectbox(
        "Severity", ["", "debug", "info", "warning", "error", "critical"]
    )
    if st.button("Refresh logs"):
        reset_cursor("logs")
    try:
        page = paged_request(
            "logs",
            api.list_logs,
            nonempty_params(service=service, environment=environment, level=level),
        )
        columns = [
            "timestamp",
            "service",
            "environment",
            "level",
            "message",
            "event_id",
        ]
        st.dataframe(
            [{key: item.get(key) for key in columns} for item in page["items"]],
            use_container_width=True,
        )
    except ApiError as error:
        show_error(error)


def anomalies_page(api: SentinelStreamClient) -> None:
    st.header("Anomalies")
    a, b, c = st.columns(3)
    severity = a.selectbox("Severity", ["", "low", "medium", "high", "critical"])
    anomaly_type = b.text_input("Anomaly type")
    rule_id = c.text_input("Rule ID")
    if st.button("Refresh anomalies"):
        reset_cursor("anomalies")
    try:
        page = paged_request(
            "anomalies",
            api.list_anomalies,
            nonempty_params(
                severity=severity, anomaly_type=anomaly_type, rule_id=rule_id
            ),
        )
        lookup = api.log_lookup()
        rows = []
        for finding in page["items"]:
            source = lookup.get(str(finding.get("event_id")), {})
            rows.append(
                {
                    "severity": finding.get("severity"),
                    "rule": finding.get("rule_id"),
                    "type": finding.get("anomaly_type"),
                    "service": source.get("service", "Unavailable"),
                    "event timestamp": source.get("timestamp", "Unavailable"),
                    "title": finding.get("title"),
                }
            )
        st.dataframe(rows, use_container_width=True)
        st.caption(
            "Service and event time are joined in the UI through the public logs API."
        )
    except ApiError as error:
        show_error(error)


def incidents_page(api: SentinelStreamClient) -> None:
    st.header("Incidents")
    a, b, c = st.columns(3)
    service = a.text_input("Service")
    environment = b.text_input("Environment")
    severity = c.selectbox(
        "Highest severity", ["", "low", "medium", "high", "critical"]
    )
    if st.button("Refresh incidents"):
        reset_cursor("incidents")
    try:
        page = paged_request(
            "incidents",
            api.list_incidents,
            nonempty_params(
                service=service, environment=environment, highest_severity=severity
            ),
        )
        items = page["items"]
        rows = [
            {
                "id": item.get("id"),
                "severity": item.get("highest_severity"),
                "service": item.get("service"),
                "finding count": item.get("finding_count"),
                "first seen": item.get("started_at"),
                "last seen": item.get("last_seen_at"),
            }
            for item in items
        ]
        st.dataframe(rows, use_container_width=True)
        if items:
            labels = {
                str(item["id"]): f"{item['service']} · {item['id']}" for item in items
            }
            selected = st.selectbox("Incident details", labels, format_func=labels.get)
            detail = api.get_incident(selected)
            st.subheader("Incident summary")
            st.json({key: value for key, value in detail.items() if key != "findings"})
            st.subheader("Ordered findings")
            findings = sorted(
                detail.get("findings", []), key=lambda item: item.get("position", 0)
            )
            st.dataframe(findings, use_container_width=True)
    except ApiError as error:
        show_error(error)


def demo_page(api: SentinelStreamClient) -> None:
    st.header("Demo ingestion")
    with st.form("demo_log"):
        service = st.text_input("Service", "payments-api")
        environment = st.text_input("Environment", "demo")
        level = st.selectbox("Severity", ["error", "critical", "warning", "info"])
        message = st.text_area("Message", "Payment provider returned an error")
        submitted = st.form_submit_button("Submit sample log")
    if submitted:
        try:
            result = api.ingest_log(
                {
                    "timestamp": datetime.now(UTC).isoformat(),
                    "service": service,
                    "environment": environment,
                    "level": level,
                    "message": message,
                    "metadata": {},
                }
            )
            st.success(f"Accepted event {result.get('event_id', '')}")
            st.info(
                "HTTP 202 confirms queue placement only. Processing is asynchronous; "
                "refresh a page when ready."
            )
        except ApiError as error:
            show_error(error)
    if st.button("Refresh demo page"):
        st.rerun()


def about_page() -> None:
    st.header("About")
    st.markdown(
        """
SentinelStream is a production-oriented portfolio project built with FastAPI,
Streamlit, PostgreSQL, SQLAlchemy, Alembic, asyncio, Docker, and strict Python typing.

Its Clean Architecture keeps domain rules independent: presentation calls application
contracts, infrastructure implements persistence and queues, and the domain imports no
framework. The pipeline is deterministic: validate → queue → detect → atomically
persist log and findings → generate incidents. Stable ordering and identities make
repeated processing understandable and testable.
"""
    )


def main() -> None:
    st.set_page_config(page_title="SentinelStream", page_icon="🛡️", layout="wide")
    st.sidebar.title("SentinelStream")
    st.sidebar.caption(f"Backend: {BACKEND_URL}")
    page = st.sidebar.radio("Navigation", PAGES)
    api = client()
    if page == "Overview":
        overview(api)
    elif page == "Logs":
        logs_page(api)
    elif page == "Anomalies":
        anomalies_page(api)
    elif page == "Incidents":
        incidents_page(api)
    elif page == "Demo":
        demo_page(api)
    else:
        about_page()


if __name__ == "__main__":
    main()
