# SentinelStream — Current State

## Current Status

Days 1–8 are complete and committed. Day 9 connects deterministic single-event anomaly
detection to the background worker and persists each event with all findings atomically.
Day 9 remains uncommitted pending review.

## Processing Flow

```text
HTTP validation → trusted LogEvent → bounded queue → background worker
→ deterministic detector → one PostgreSQL transaction
    ├── log_events row
    └── zero or more anomaly_findings rows
```

HTTP 202 continues to mean queue acceptance only. It does not confirm detection or
database commit.

## Day 9 Persistence

`DetectAndPersistLogEventProcessor` calls the detector once, rejects a result whose event
UUID differs from the source event, then delegates the event and complete ordered
finding tuple to a focused transactional persistence port.

`SqlAlchemyDetectionPersistence` creates one session and one transaction per queued
event. It inserts and flushes the source event before adding findings. The transaction
context commits once on success and rolls back the event and every finding on failure.
Normal events commit with zero findings; one anomalous event may commit several.

`anomaly_findings` stores PostgreSQL UUID identities, source-event foreign keys, stable
anomaly/severity strings, versioned rule IDs, bounded titles, JSONB evidence arrays, and
timezone-aware persistence timestamps. `UNIQUE(event_id, rule_id)` prevents duplicate
rows for the same rule execution. The foreign key uses `ON DELETE CASCADE`.

## Migration State

Alembic head is `20260722_0002`. Operators must apply it explicitly before starting the
updated worker. Its downgrade removes `anomaly_findings` and all persisted findings but
preserves `log_events` and unrelated tables. Application startup never runs migrations
or `create_all`.

## Current Boundary

Findings are persisted but are not exposed through a public API. The existing log query
API remains event-only. Worker processing failures are isolated so later events can
continue, but failed events may be lost because the in-process queue has no retry,
dead-letter, replay, durable-broker, or outbox behavior.

No anomaly query API, incident grouping, rolling-window/statistical detection, alerting,
explanation generation, LLM use, authentication, or Day 10 functionality exists.
