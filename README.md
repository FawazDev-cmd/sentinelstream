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


## Query persisted anomalies

```bash
curl "http://127.0.0.1:8000/api/v1/anomalies"
curl "http://127.0.0.1:8000/api/v1/anomalies?anomaly_type=high_latency&severity=critical&limit=2"
curl "http://127.0.0.1:8000/api/v1/anomalies?event_id=<event_uuid>"
curl "http://127.0.0.1:8000/api/v1/anomalies?limit=2&cursor=<next_cursor>"
```

Supported filters are exact `event_id`, `anomaly_type`, `severity`, and `rule_id`, plus
inclusive `created_at` bounds through `start_time` and `end_time`. Results are fixed to
`created_at DESC, id DESC`. Limits range from 1 to 100 with a default of 50. Cursors are
opaque URL-safe encoded values, not encrypted or signed, and responses have no total
count.

The endpoint is read-only and returns no source log messages or metadata. Migration
`20260722_0002` must be applied. HTTP 202 ingestion remains queue acceptance only. There
is no acknowledgement, resolution, mutation, aggregation, incident handling, alerting,
or LLM explanation functionality.

## Deterministic incident grouping

Day 11 provides a pure in-memory grouper for persisted anomaly findings enriched with
source-event service, environment, and occurrence time. The grouping key is
`service + environment + anomaly_type`. The default policy requires two findings and
allows a five-minute adjacent gap.

Adjacent-gap clustering means 12:00, 12:04, and 12:08 remain one candidate. A gap
exactly at five minutes is included; a larger gap starts another cluster. Candidates
preserve aligned finding/event/rule tuples, aggregate highest severity by explicit rank,
and use deterministic ordering. Duplicate finding UUIDs are rejected.

No worker or scheduler invokes grouping yet. Incident candidates are not persisted and
there is no incident API, acknowledgement, resolution, alerting, or LLM explanation.
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