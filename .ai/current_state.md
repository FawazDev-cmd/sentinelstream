# SentinelStream — Current State

## Project

SentinelStream is a portfolio-first real-time log intelligence platform that ingests structured logs, persists them asynchronously, retrieves logs and anomalies through stable cursor pagination, detects deterministic anomalies, groups related findings into incident candidates, and persists incidents with deterministic identity and ordered anomaly memberships.

## Completed Milestones

Completed, committed, and pushed:

* Day 1 — Project Foundation
* Day 2 — Log Domain Contracts
* Day 3 — Ingestion Schemas and Normalization
* Day 4 — Asynchronous Queue and Worker Lifecycle
* Day 5 — PostgreSQL Persistence Foundation
* Day 6 — Alembic Migration Foundation
* Day 7 — Log Query API and Cursor Pagination
* Day 8 — Single-Event Anomaly Rules Engine
* Day 9 — Anomaly Persistence and Worker Integration
* Day 10 — Anomaly Query API and Cursor Pagination
* Day 11 — Deterministic Incident Grouping Foundation
* Day 12 — Incident Persistence Foundation

## Current Capabilities

SentinelStream currently provides:

* FastAPI application factory
* centralized validated settings
* structured JSON logging
* `GET /health`
* `POST /api/v1/logs`
* `GET /api/v1/logs`
* `GET /api/v1/anomalies`
* `GET /api/v1/incidents`
* `GET /api/v1/incidents/{incident_id}`
* immutable log-event domain values
* bounded asynchronous ingestion queue
* managed background worker
* PostgreSQL persistence
* Alembic schema management
* deterministic anomaly detection
* atomic event-and-anomaly persistence
* deterministic log and anomaly cursor pagination
* exact anomaly filtering
* deterministic incident grouping
* adjacent-gap clustering
* immutable incident candidates
* deterministic UUIDv5 incident identity
* normalized incident and membership persistence
* ordered incident membership storage
* atomic incident persistence
* idempotent repeat persistence
* one-finding-to-one-incident database enforcement
* read-only incident list and detail API
* fixed incident keyset pagination and exact filters
* ordered safe incident detail memberships
* Alembic revision 0003
* 382 passing non-integration tests
* guarded PostgreSQL integration tests
* Ruff and strict mypy verification

## Current Milestone

Phase 6 — Incident Intelligence Foundation

### Active Task

Day 13 — Incident Query API and Cursor Pagination implemented

## Objective

Expose persisted incidents through safe, deterministic, read-only query paths.

Day 13 must establish:

* immutable persisted-incident read model
* immutable incident-membership read model
* incident query criteria
* incident cursor model and codec
* narrow incident reader protocol
* SQLAlchemy incident reader
* stable keyset pagination
* exact filtering
* ordered membership loading
* typed FastAPI response schemas
* incident list endpoint
* incident detail endpoint
* dependency wiring
* focused unit tests
* guarded PostgreSQL integration tests
* documentation

## Public Endpoints

Add:

```text
GET /api/v1/incidents
GET /api/v1/incidents/{incident_id}
```

### List endpoint

Returns:

```json
{
  "items": [],
  "next_cursor": null
}
```

The list response should contain incident summaries only.

It must not contain all membership rows by default.

### Detail endpoint

Returns:

* one persisted incident
* its ordered anomaly-finding memberships
* safe anomaly summary fields

It must not expose:

* source log message
* source metadata
* SQLAlchemy records
* database credentials
* raw internal exceptions

## List Ordering

Use fixed ordering:

```text
last_seen_at DESC
id DESC
```

Use keyset pagination only.

Do not use SQL offset pagination.

## List Filters

Support exact filters for:

```text
service
environment
anomaly_type
highest_severity
started_after
started_before
last_seen_after
last_seen_before
minimum_finding_count
limit
cursor
```

Time bounds should be inclusive.

Combined filters use AND semantics.

## Detail Membership Ordering

Memberships must be returned by:

```text
position ASC
```

Membership order must match the original incident candidate finding order.

## Day 13 Boundaries

Do not implement:

* acknowledgement
* resolution
* assignment
* comments
* incident mutation endpoints
* incident deletion endpoints
* alerting
* notifications
* automatic grouping orchestration
* worker integration
* scheduled grouping
* LLM explanation
* statistical incident analysis
* Day 14 functionality

## Immediate Next Step

Give Codex the complete Day 13 Incident Query API and Cursor Pagination specification.

Do not implement Day 14.
