# Architecture

## Direction

The planned logical layers are Domain, Application, Infrastructure,
Presentation, Monitoring, and Shared Configuration. Dependencies point inward:
presentation and infrastructure adapt application contracts, while the domain
remains independent of web, persistence, queue, dashboard, and model-provider
frameworks.

Day 1 creates only the layers with concrete responsibilities:

- `app.presentation` owns FastAPI construction and HTTP routes.
- `app.monitoring` owns standard-library logging configuration.
- `app.shared` owns process configuration.

Future layer packages will be added only when a milestone supplies real behavior.

## Application construction

`create_app` accepts optional settings, configures logging, stores the active
settings on application state, and registers the health router. The exported
`app` instance supports Uvicorn without introducing startup hooks.

## Health semantics

`GET /health` proves only that the HTTP process can respond. It reports service
name and version from active settings and intentionally checks no future external
dependencies.

## Ingestion boundary

Day 3 keeps external schemas in presentation and converts them to an application `IngestionInput`. The application `IngestionService` owns explicit provider-level aliases, UUID selection, clock use, UTC normalization, and construction of the domain `LogEvent`. FastAPI resolves the service from application state populated by `create_app`, allowing deterministic injection without global mutable business state.

The application-level `Clock` protocol separates server receipt time from wall-clock access. `SystemClock` returns UTC; the service still validates awareness and normalizes any aware clock value to UTC. The Day 3 terminal behavior returns the constructed event only—there is no queue or persistence.

## In-process queue and worker lifecycle

Day 4 adds application protocols for trusted-event queueing and asynchronous processing. `InMemoryEventQueue` is an infrastructure adapter over a private bounded `asyncio.Queue`; publication uses `put_nowait` and translates capacity exhaustion into `EventQueueFullError`.

`create_app` constructs one shared queue for `IngestionService` and `EventWorker`. FastAPI lifespan starts one worker task, attempts bounded graceful draining with `queue.join()` during shutdown, then cancels and awaits the worker. Ordinary processor failures are isolated inside the worker and logged using only approved event identifiers. The queue is process-local and non-durable; there are no retries, dead-letter handling, persistence, or multiple production workers.

## PostgreSQL persistence foundation

Day 5 adds a one-method `LogEventRepository` application protocol and `PersistenceEventProcessor`. Infrastructure owns the SQLAlchemy 2.x declarative base, PostgreSQL-specific ORM model, explicit domain mapper, async engine/session construction, transactional repository, and non-destructive schema helper. The domain remains SQLAlchemy-free.

The ORM uses `event_metadata` as its Python attribute because `metadata` is reserved by SQLAlchemy declarative models; the physical PostgreSQL column remains `metadata` and uses JSONB. Frozen domain mappings and tuples are explicitly converted to mutable dictionaries and lists.

When no processor is injected, `create_app` constructs one engine and session factory for the transactional detection-persistence adapter and log reader. Internally created engines are application-owned and disposed during shutdown even after a drain timeout. Operators must apply Alembic migrations before startup. An external engine remains caller-owned. Injecting a processor bypasses database and detector construction.

Repository operations open one session per event, commit once, roll back ordinary commit failures, and propagate errors. Duplicate UUIDs remain primary-key failures; there are no upserts, retries, dead-letter recovery, or query methods.


## Alembic migration authority

Day 6 makes version-controlled Alembic revisions authoritative for PostgreSQL schema evolution. The Alembic environment imports the single infrastructure `Base` and explicit ORM model, resolves the database URL through centralized validated settings, and supports offline SQL plus online asyncpg execution with an independently owned migration engine.

The application lifecycle never invokes Alembic or `Base.metadata.create_all`. Missing migrations therefore surface later as asynchronous persistence failures; they are not automatically repaired. Revision `20260722_0001` owns the `log_events` table and six indexes. Its downgrade deliberately removes only those objects and destroys rows in that table.

## Persisted log read boundary

Day 7 adds immutable application query, cursor, and page values plus the narrow `LogEventReader` protocol. Cursor ordering is fixed to `(timestamp DESC, event_id DESC)` and its predicate uses older timestamps or lower UUIDs at the same timestamp. Cursors are strict URL-safe Base64 JSON tokens containing only UTC timestamp and UUID; they are opaque API values but are not encrypted or signed.

`SqlAlchemyLogEventReader` shares the production session factory, creates a fresh session per call, applies exact and inclusive filters, fetches `limit + 1`, and never commits. Infrastructure explicitly maps ORM records back into domain events and allows invalid persisted data to fail visibly. Presentation validates query parameters and maps malformed cursors to HTTP 422.

No migration was added because revision `20260722_0001` already contains the required timestamp, UUID-primary-key, and composite service/timestamp indexes. No total count, offset pagination, arbitrary ordering, full-text search, or metadata search exists.

## Deterministic single-event anomaly detection

Day 8 adds framework-independent anomaly types, explicitly ranked severities, bounded
immutable findings, and immutable per-event detection results in the domain. The
application owns synchronous rule and detector protocols, an immutable validated
policy, four deterministic rules, explicit default construction, and ordered
orchestration with duplicate rule-ID rejection.

Default rules run in stable order: `single_event.error_level.v1`,
`single_event.server_error_status.v1`, `single_event.exception_present.v1`, and
`single_event.high_latency.v1`. One event may produce all four findings. Evidence names
only triggering fields and thresholds; event messages, exception-message contents, and
metadata are excluded. Default thresholds are 1000 ms high latency, 5000 ms critical
latency, status 500 server error, and status 550 critical server error, exposed through
centralized `SENTINELSTREAM_` settings.

Day 9 wires detection into the background worker and persists findings atomically with the source event. Findings still have no public API. No historical, statistical,
incident, alerting, explanation, or LLM behavior exists.

## Atomic anomaly persistence and worker integration

Day 9 adds the focused `DetectionPersistence` application port and
`DetectAndPersistLogEventProcessor`. The processor detects exactly once, verifies the
result UUID matches the source event, and passes the unchanged event plus every ordered
finding to persistence. Detection and persistence errors propagate to the existing
worker boundary, which safely completes the queue task and continues with later events.

`SqlAlchemyDetectionPersistence` owns a fresh session and one transaction per event. It
adds and flushes the event before mapping findings into the same session; the SQLAlchemy
transaction context performs the sole commit or automatic rollback. Repositories do not
commit within this path. Normal events therefore persist without findings, while any
finding failure rolls back the source event.

Revision `20260722_0002` owns `anomaly_findings`, its UUID primary key, JSONB evidence,
timezone-aware creation time, source-event foreign key with cascade deletion, four
single-column indexes, and unique `(event_id, rule_id)` constraint. Downgrading to 0001
destroys findings but leaves `log_events` intact. Migrations remain explicit operator
actions.

Default construction uses Day 8 settings and rule order, the rule-based detector, the
transactional adapter, and the existing single worker. Processor injection bypasses
database and detector construction. HTTP 202 still represents queue acceptance only.
There is no anomaly read API, retry, replay, incident logic, rolling-window detection,
alerting, or LLM explanation behavior.

## Persisted anomaly read boundary

Day 10 adds immutable persisted-finding, query, cursor, and page values plus the narrow
`AnomalyFindingReader` protocol. The persisted read value is deliberately separate from
the Day 8 detector finding and includes only storage identity, source-event identity,
stable enums, rule/title, safe evidence, and persistence time.

`SqlAlchemyAnomalyFindingReader` shares the production session factory, opens a fresh
session per request, and issues one SELECT without commits or source-event joins. Exact
filters combine with AND semantics. Ordering is fixed to `(created_at DESC, id DESC)`;
the matching cursor predicate selects older timestamps or lower UUIDs at equal time.
The reader fetches `limit + 1` and derives the next cursor from the final returned item.

Presentation owns `GET /api/v1/anomalies`, typed response schemas, cursor conversion,
query validation, and a generic safe 500 response. The endpoint returns no source log
message, metadata, total count, mutation state, aggregation, or incident information.
No schema revision was needed beyond `20260722_0002`.
## Deterministic incident grouping foundation

Day 11 adds framework-independent incident grouping keys and immutable candidate values
in the domain, with input, policy, protocol, and deterministic grouper behavior in the
application. Infrastructure and presentation have no incident implementation.

A grouping key contains only service, environment, and anomaly type. Source event time,
not anomaly persistence time, drives clustering. Persistence time and finding UUID are
stable tie-breakers after occurrence time. Clustering compares each finding to its
immediate predecessor, so chains may span longer than the configured maximum gap when
every adjacent gap remains within it. The exact boundary is inclusive.

The default policy is a five-minute maximum adjacent gap and a minimum of two findings.
Candidate finding, event, and rule tuples are constructed from the same sorted cluster
and remain index-aligned. Highest severity uses the existing explicit rank. Duplicate
finding UUIDs fail the complete call, while duplicate event UUIDs are permitted.
Candidates are sorted by occurrence bounds, key values, and first finding UUID.

This capability is currently an explicitly invoked pure in-memory service. No worker or
scheduler invokes it; no candidate is persisted or exposed through an API. There is no
operational incident status, acknowledgement, resolution, alerting, or LLM explanation.
## Incident persistence foundation

Day 12 adds deterministic UUIDv5 incident identity and a narrow `IncidentPersistence`
application port. Identity uses length-delimited service/environment values, stable
anomaly type, canonical UTC occurrence bounds, and ordered finding UUIDs. It performs no
I/O or clock access and excludes severity, rule IDs, evidence, and persistence time.

Infrastructure maps each candidate into one `IncidentRecord` plus zero-based ordered
`IncidentFindingRecord` rows. One fresh session and transaction adds and flushes the
incident before all memberships. Sequential identical persistence strictly verifies the
stored immutable incident and membership sequence before returning the same UUID.
Mismatches fail visibly; uniqueness on finding UUID prevents cross-incident assignment.

Revision `20260722_0003` owns the incident tables, occurrence/count/position checks,
focused indexes, cascade incident deletion, and restricted assigned-finding deletion.
Downgrade preserves revision 0002 log and anomaly objects. No worker, lifespan,
scheduler, or presentation dependency constructs or invokes incident persistence.
## Incident query API and cursor pagination

Day 13 exposes persisted incidents through read-only list and detail endpoints. The list
uses fixed `last_seen_at DESC, id DESC` ordering, matching keyset predicates, and an
opaque cursor containing only the final returned incident's timestamp and UUID. It
fetches `limit + 1`, returns no total count, and never uses offset pagination.

Exact service, environment, anomaly type, and highest-severity filters combine with
inclusive occurrence-time bounds and minimum finding count. Detail loading uses one
incident SELECT and one explicit membership-to-anomaly join ordered by zero-based
position. Mapping rejects incomplete, duplicated, noncontiguous, mismatched, unknown-
enum, or naive-timestamp state.

Responses expose incident summaries and safe persisted anomaly fields only. They never
load or expose source messages or metadata. The reader shares the existing session
factory, performs no commits, and is replaceable by a database-free injected fake.
Revision 0003 remains required; Day 13 adds no migration. There are no mutation,
acknowledgement, resolution, assignment, grouping-orchestration, worker, or explanation
paths.

## Explicit incident generation orchestration

Day 14 adds an explicitly constructed application use case that reads unassigned anomaly
findings for an inclusive source-event-time window, loads every internal keyset page,
then invokes the deterministic grouper exactly once. Grouping is deliberately not
page-local because an adjacent-gap cluster may cross any database page boundary.

The eligible reader joins anomaly findings to source log-event context, excludes rows
already present in `incident_findings` with `NOT EXISTS`, and orders by source event
timestamp, finding creation time, then finding UUID ascending. Messages and metadata
remain outside the application value. The internal cursor is not an HTTP token.

Candidates persist sequentially in grouper order. Each candidate has its own Day 12
transaction; a complete generation run is not atomic. Execution is fail-fast with no
retries or compensating deletes. On retry, committed memberships are excluded and
remaining unassigned findings may be processed. Database uniqueness is final protection
for concurrent assignment; Day 14 adds no locks or claims.

Nothing invokes generation automatically. There is no scheduler, lifecycle/worker
integration, HTTP or CLI trigger, background loop, or run-history storage. Revision
0003 remains required and no migration is added.

## Runtime incident generation integration

Day 15 extends the existing event processor sequence to detect anomalies, persist the log
and findings atomically, then synchronously execute the existing `GenerateIncidents`
use case before processing returns. Generation is skipped when detection produces no
findings. Its inclusive request window is [source event timestamp - configured lookback, source event timestamp] and uses no wall clock.

Production constructs the eligible reader, deterministic grouper, incident persistence,
and generator from the same shared async session factory already used by detection
persistence and query readers. No additional engine or factory is created. Generation
errors propagate through the existing worker failure boundary without suppression or
retry.

There is no scheduler, startup/lifespan generation, deferred task, concurrent gather,
HTTP or CLI trigger, retry, lock, lease, acknowledgement, resolution, or alerting.

## Runtime incident window correction

The runtime composition converts the validated
`incident_generation_lookback_seconds` setting into a timedelta once and injects it
into the event processor. Valid configuration is 1 through 86400 seconds, defaulting to
3600. After anomaly persistence, the processor synchronously requests the inclusive
event-time window `[event.timestamp - lookback, event.timestamp]`.

The existing eligible reader still excludes assigned findings. This enables nearby
unassigned events to enter one generation run but does not extend or merge persisted
incidents. There is no scheduler or retry. Worker failures propagate at the processing
boundary; HTTP 202 may already have been returned because it represents queue acceptance.

## Structured processing observability

Day 16 emits structured lifecycle records for processing start, anomaly detection,
atomic event/anomaly persistence, incident generation, and completion or failure. The
source event UUID is reused as the stable processing correlation ID. Every lifecycle
record includes safe service, environment, and event-time context but never the source
message, metadata, raw payload, database URL, or exception text.

Processing duration uses an injected monotonic clock and is reported in milliseconds.
Successful completion includes log-style metric fields for logs processed, anomalies
detected, incidents generated, outcome, and total duration. Failure records preserve
exception propagation while reporting only the failure stage, exception type, safe
generic message, and elapsed duration.

The worker emits started, stopping, and stopped lifecycle records and a safe processor
failure record. This adds visibility only: queue completion, continuation after ordinary
processing failure, cancellation, shutdown, business ordering, and HTTP 202 semantics
remain unchanged. There is no metrics endpoint, external telemetry dependency, retry,
dead-letter queue, or tracing backend.
