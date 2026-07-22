# SentinelStream — Current State

## Current Status

Days 1–5 are complete. SentinelStream accepts validated single log events, places trusted `LogEvent` objects into a bounded non-durable in-process queue, and asynchronously persists them to PostgreSQL through one managed worker.

## Day 5 — PostgreSQL Persistence Foundation

The implemented flow is:

```text
HTTP request
→ validation and normalization
→ trusted LogEvent
→ bounded in-process queue
→ background worker
→ PersistenceEventProcessor
→ LogEventRepository
→ PostgreSQL through SQLAlchemy async APIs and asyncpg
```

HTTP 202 still means queue placement only; it does not confirm a database commit. Persistence failures are isolated and safely logged by the worker. There is currently no retry or dead-letter recovery, so an event whose asynchronous persistence fails is lost after logging.

The PostgreSQL `log_events` model uses native UUID and JSONB types, timezone-aware timestamps, domain-aligned string lengths, and practical retrieval indexes. Startup uses non-destructive `Base.metadata.create_all` only as a temporary local-development strategy. Alembic and production migration management are not implemented.

Internally created engines are initialized and disposed by the application. Caller-injected engines are neither schema-initialized nor disposed. Injecting an event processor bypasses database creation entirely.

The queue remains process-local and non-durable. Process crashes may lose queued or processing events. There is no anomaly detection, incident generation, querying API, retry, dead-letter queue, migration system, or Day 6 functionality.
