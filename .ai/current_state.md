# SentinelStream — Current State

## Current Status

Days 1–7 are complete and committed. Day 8 implements a standalone deterministic
single-event anomaly rules engine and remains uncommitted pending review.

SentinelStream validates and queues trusted log events, asynchronously persists them to
PostgreSQL, and exposes cursor-paginated retrieval of persisted events. Day 8 detection
can evaluate a trusted `LogEvent` directly but is not connected to that runtime flow.

## Day 8 — Single-Event Anomaly Rules Engine

The domain now provides stable anomaly types, explicitly ranked severities, bounded
immutable findings, and immutable detection results. `DetectionResult` preserves the
evaluated event UUID and reports whether findings exist plus their highest severity.

The application provides narrow synchronous rule and detector protocols, an immutable
validated `DetectionPolicy`, a deterministic `RuleBasedAnomalyDetector`, and explicit
default rule construction. Duplicate rule IDs and empty rule collections are rejected;
every configured rule runs exactly once in stable order and unexpected rule failures
propagate.

The four versioned default rules are:

* `single_event.error_level.v1`
* `single_event.server_error_status.v1`
* `single_event.exception_present.v1`
* `single_event.high_latency.v1`

Default thresholds are 1000 ms for high latency, 5000 ms for critical latency, status
500 for server errors, and status 550 for critical server errors. Centralized
`SENTINELSTREAM_` settings expose each threshold and reject invalid or inconsistent
values.

One event may produce multiple findings. Evidence contains only bounded triggering
field values and configured thresholds. Log messages, exception-message contents,
metadata, arbitrary exception objects, and mutable event state are excluded.

## Runtime Boundary

Detector output is not persisted and detection is not connected to ingestion or the
background worker. No anomaly endpoint, anomaly database model, migration, historical
or statistical detection, incident logic, alerting, explanation generation, or LLM
integration exists.

The Day 6 migration remains the only Alembic revision. No dependency was added for Day
8. Existing ingestion, persistence, migration, query, and API behavior remains
unchanged.

## Next Milestone

Day 9 is not implemented.
