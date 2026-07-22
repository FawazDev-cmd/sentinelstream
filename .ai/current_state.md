# SentinelStream — Current State

## Current Status

Days 1–7 are complete. SentinelStream validates and queues trusted log events, asynchronously persists them to PostgreSQL, and exposes cursor-paginated retrieval of persisted events.

## Day 7 — Log Query API and Cursor Pagination

`GET /api/v1/logs` retrieves persisted events through a framework-independent `LogEventReader` contract and SQLAlchemy read adapter.

Supported filters are exact `service`, `environment`, and normalized `level`, plus inclusive `start_time` and `end_time`. Filters combine with AND semantics. Results always use `timestamp DESC, event_id DESC` ordering.

Pagination uses an opaque URL-safe Base64 JSON cursor containing only the final returned timestamp and UUID. Tokens are deterministic and strictly validated, but encoded rather than encrypted or signed. The default limit is 50, the accepted range is 1–100, and no total count is returned.

The reader uses fresh sessions, performs no commits, requests `limit + 1`, and maps ORM records explicitly back into trusted `LogEvent` objects. Invalid cursors and query criteria return HTTP 422; unexpected database failures remain HTTP 500.

No schema change was needed, so Alembic history remains at `20260722_0001`. Migrations must be applied before persistence and retrieval. HTTP 202 still means in-process queue placement only.

There is no full-text search, metadata filtering, aggregation, count query, offset pagination, arbitrary sorting, anomaly detection, retry, authentication, or Day 8 functionality.
