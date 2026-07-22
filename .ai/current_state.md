# SentinelStream — Current State

## Current Status

Days 1–9 are complete and committed. Day 10 adds a read-only cursor-paginated API for
persisted anomaly findings and remains uncommitted pending review.

## Anomaly Query API

`GET /api/v1/anomalies` returns typed persisted findings without joining source events
or exposing log messages or metadata. Supported exact filters are `event_id`,
`anomaly_type`, `severity`, and `rule_id`. `start_time` and `end_time` apply inclusive
bounds to the persistence timestamp `created_at`; combined filters use AND semantics.

Results use fixed `created_at DESC, id DESC` ordering and keyset pagination. The default
limit is 50, the accepted range is 1–100, and no total count is returned. The opaque
URL-safe Base64 cursor contains only canonical UTC creation time and finding UUID; it is
strictly validated but is not encrypted or signed.

The read model preserves storage/source UUIDs, stable anomaly and severity enums,
versioned rule IDs, safe evidence tuples, and UTC creation time. Infrastructure performs
one SELECT through a fresh session, uses `limit + 1`, and maps records explicitly. It
never commits, joins source logs, uses offset pagination, or disposes the shared engine.

Production constructs the anomaly and log readers from the same session factory. Tests
can inject a fake anomaly reader with an injected processor and avoid PostgreSQL.

## Runtime and Persistence Semantics

HTTP 202 ingestion still means queue acceptance only, not detection or commit. Migration
`20260722_0002` remains required; Day 10 adds no migration. Findings are query-only:
there is no anomaly creation, mutation, acknowledgement, resolution, count,
aggregation, incident grouping, rolling-window/statistical detection, alerting,
explanation generation, LLM use, authentication, or Day 11 functionality.