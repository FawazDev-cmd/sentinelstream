# SentinelStream

SentinelStream validates individual log events, places them into a bounded non-durable
queue, detects deterministic single-event anomalies in the background worker, and
atomically persists each event with zero or more findings in PostgreSQL. Persisted logs
are available through cursor-paginated retrieval.

## Setup and migrations

Configure `SENTINELSTREAM_DATABASE_URL`, then run:

```bash
uv sync
uv run alembic upgrade head
uv run uvicorn app.presentation.api.main:app --host 127.0.0.1 --port 8000
```

Migration `20260722_0002` is required for anomaly persistence. Migrations are explicit
operator actions; application startup does not create or migrate tables. Downgrading to
`20260722_0001` removes all anomaly findings while preserving `log_events`.

HTTP 202 from `POST /api/v1/logs` means queue placement only. It does not confirm
detection or database commit.

## Query persisted logs

```bash
curl "http://127.0.0.1:8000/api/v1/logs"
curl "http://127.0.0.1:8000/api/v1/logs?service=payments-api&level=error&limit=25"
curl "http://127.0.0.1:8000/api/v1/logs?start_time=2026-07-22T00:00:00Z&end_time=2026-07-22T23:59:59Z"
curl "http://127.0.0.1:8000/api/v1/logs?limit=25&cursor=<next_cursor>"
```

Results are newest first by event timestamp and UUID. The default limit is 50 and the
maximum is 100. Cursors are encoded opaque tokens, not encrypted or signed. Supported
filters are exact `service`, `environment`, and `level`, plus inclusive event-time
bounds. There is no count, partial matching, full-text/metadata search, aggregation,
arbitrary sorting, or offset pagination.

## Detection and atomic persistence

The stable versioned rules detect error/critical levels, server-error status,
exception-field presence, and high latency. Defaults are 1000 ms high latency, 5000 ms
critical latency, status 500 server error, and status 550 critical server error.
Corresponding `SENTINELSTREAM_` settings may override them.

For each queued event, detection runs once and one PostgreSQL transaction inserts the
source event followed by every finding. Normal events commit with zero findings. A
multi-signal event may commit several findings. Any event or finding insertion failure
rolls back the complete transaction.

Findings store stable rule IDs and JSON evidence arrays. `UNIQUE(event_id, rule_id)`
prevents duplicate rows for one event and rule; deleting an event cascades to its
findings. Evidence excludes log messages, exception-message contents, and metadata.

Findings have no public query API. Worker failures may lose events because the queue is
process-local and there are no retries, dead-letter handling, replay, outbox, or durable
broker. There is no incident grouping, rolling-window/statistical detection, alerting,
explanation generation, or LLM involvement.

## Quality checks

```bash
uv run pytest
uv run pytest -m "not integration"
uv run pytest -m integration -rs
uv run ruff check .
uv run ruff format --check .
uv run mypy app tests
git diff --check
```