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

## Incident persistence foundation

Day 12 persists immutable incident candidates using deterministic UUIDv5 identities.
Identity includes service, environment, anomaly type, canonical UTC occurrence bounds,
and ordered finding UUIDs. One transaction stores the incident and zero-based ordered
memberships. Repeating an identical candidate returns the same UUID without duplicates;
conflicting stored state fails explicitly.

Apply Alembic revision `20260722_0003`. One anomaly finding may belong to only one
persisted incident. Incident deletion cascades memberships, while deletion of an
assigned finding is restricted. Downgrading to 0002 removes incident data but preserves
logs and anomaly findings.

Incident persistence is not invoked automatically. There is no grouping scheduler,
worker integration, incident API, acknowledgement, resolution, assignment, alerting, or
LLM explanation functionality.

## Query persisted incidents

```bash
curl "http://127.0.0.1:8000/api/v1/incidents"
curl "http://127.0.0.1:8000/api/v1/incidents?service=payments-api"
curl "http://127.0.0.1:8000/api/v1/incidents?highest_severity=critical&limit=20"
curl "http://127.0.0.1:8000/api/v1/incidents?cursor=<opaque>"
curl "http://127.0.0.1:8000/api/v1/incidents/<incident_uuid>"
```

List ordering is fixed to `last_seen_at DESC, id DESC` and uses opaque keyset cursors
containing those two values. Exact filters combine with AND semantics; started and
last-seen time bounds are inclusive, and `minimum_finding_count` is at least two.
Limits range from 1 to 100 and default to 50. Responses contain no total count and the
reader uses no SQL offset.

Detail findings preserve zero-based membership order and expose safe anomaly identity,
classification, rule, title, evidence, event correlation, and persistence time only.
Source messages and metadata are neither loaded nor returned. Alembic revision
`20260722_0003` is required. There are no incident mutation, acknowledgement,
resolution, assignment, automatic grouping, worker integration, alerting, or LLM
explanation endpoints.


## Explicit incident generation

Day 14 provides a framework-independent `GenerateIncidents` use case for callers that
explicitly supply an inclusive source-event-time window. The eligible reader joins
anomalies to source events, excludes already assigned finding UUIDs, and traverses them
using internal ascending keyset pages:

```text
event timestamp ASC, finding creation time ASC, finding UUID ASC
```

The service loads the complete window before one deterministic grouping call, so page
boundaries cannot split adjacent-gap clusters. Batch size controls reads only. Candidates
persist sequentially and fail fast. Persistence is atomic per candidate, not across a
whole run; a retry excludes previously assigned findings and can continue remaining work
without run records or checkpoints.

This is an internal, explicitly invoked capability. It has no HTTP endpoint, scheduler,
worker/lifecycle integration, CLI, automatic execution, acknowledgement, resolution,
alerting, or LLM behavior. Alembic revision `20260722_0003` is required.


## Automatic incident generation after anomaly persistence

The production event processor now runs this deterministic sequence:

```text
persist log and anomaly findings
? generate incidents for the bounded source-event lookback window
? return processing success
```

Generation runs synchronously once, only after successful anomaly persistence and only
when findings exist. The inclusive generation window is [event timestamp - configured lookback, event timestamp]. Failures propagate without suppression or retry.

All incident-generation adapters reuse the existing application engine and async session
factory. There is no scheduler, lifecycle invocation, background generation task, HTTP
or CLI trigger, widened window, retry, acknowledgement, resolution, or alerting.


## Production processing observability

Each background event now emits structured JSON lifecycle records for processing start,
anomaly detection, persistence, incident generation, and completion or failure. The
event UUID is the stable processing correlation ID. Durations use a monotonic clock and
successful summaries include logs_processed, anomalies_detected, incidents_generated,
processing_duration_ms, and outcome fields.

Failure records contain the safe stage and exception type while the original exception
continues through the existing processing boundary. Source messages, metadata, raw
payloads, secrets, environment variables, and database URLs are not included. Worker
startup, stopping, and stopped events are also logged.

These are metric-style log fields only. SentinelStream adds no metrics endpoint,
Prometheus, OpenTelemetry, tracing backend, retry, dead-letter queue, or behavior change.

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

## Runtime incident lookback

`SENTINELSTREAM_INCIDENT_GENERATION_LOOKBACK_SECONDS` configures the deterministic
runtime window and defaults to 3600 seconds. Valid values are 1 through 86400. The
processor uses source event time only:

```text
[event timestamp - configured lookback, event timestamp]
```

Both bounds are inclusive. Already assigned findings remain excluded, and the grouper
does not extend or merge existing incidents. Generation has no scheduler or retry.
Because HTTP 202 means queue acceptance, a response may already have been returned before
the worker encounters an anomaly-persistence or incident-generation failure.

## Local Python development

The non-container workflow remains supported:

~~~bash
uv sync --frozen
uv run alembic upgrade head
uv run uvicorn app.presentation.api.main:app --host 127.0.0.1 --port 8000
~~~

For this host workflow, set SENTINELSTREAM_DATABASE_URL to a PostgreSQL URL using
localhost rather than the Compose service hostname.

## Docker Compose quick start

Copy the safe local example, build the production image, start PostgreSQL, apply the
explicit Alembic migration, and then start the API:

~~~bash
cp .env.example .env
docker compose build
docker compose up -d postgres
docker compose run --rm api uv run alembic upgrade head
docker compose up -d api
docker compose ps
curl http://localhost:8000/health
~~~

The API never runs migrations or metadata create_all during startup. Migration failures
remain visible and prevent the one-shot migration command from succeeding. The API waits
for PostgreSQL health before starting. FastAPI and the managed ingestion worker share
one non-root API container; there is no separate worker container. Structured JSON logs
are written to stdout.

Inspect API logs with:

~~~bash
docker compose logs --no-color api
~~~

Stop containers while preserving the database volume:

~~~bash
docker compose down
~~~

To destroy the local PostgreSQL volume and all its data, use the following destructive
reset deliberately:

~~~bash
docker compose down -v
~~~

## Continuous integration gates

GitHub Actions runs three least-privilege jobs:

- quality: locked dependency sync, Ruff lint and format, strict mypy, non-integration
  tests, Alembic history/head inspection, and an automated exactly-one-head assertion;
- PostgreSQL integration: a health-checked sentinelstream_test database, Alembic upgrade,
  and the integration suite with its safety guard enabled;
- Docker build: a BuildKit production-image build without registry credentials or push.

The container image installs locked runtime dependencies with uv, excludes tests and
environment files, runs as an unprivileged user, and starts Uvicorn without reload.
