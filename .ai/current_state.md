# SentinelStream — Current State

## Project

SentinelStream is a portfolio-first real-time log intelligence platform that ingests structured logs, detects and persists anomalies, groups related findings into deterministic incident candidates, persists incidents atomically, and exposes logs, anomalies, and incidents through safe read-only APIs.

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
* Day 13 — Incident Query API and Cursor Pagination

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
* bounded asynchronous log ingestion
* managed background worker
* PostgreSQL log and anomaly persistence
* deterministic anomaly detection
* atomic event-and-anomaly persistence
* stable keyset pagination
* deterministic incident grouping
* adjacent-gap temporal clustering
* immutable incident candidates
* deterministic UUIDv5 incident identity
* atomic incident persistence
* ordered incident memberships
* idempotent incident persistence
* one-finding-to-one-incident enforcement
* read-only incident list and detail APIs
* safe dependency injection
* Alembic revisions 0001–0003
* 382 passing non-integration tests
* explicit full-window incident generation orchestration
* eligible unassigned finding traversal by source event time
* guarded PostgreSQL integration tests
* Ruff and strict mypy verification

## Current Milestone

Phase 6 — Incident Intelligence Foundation

### Active Task

Day 14 — Incident Generation Orchestration implemented

## Objective

Connect anomaly selection, deterministic grouping, and incident persistence through one framework-independent application use case.

Day 14 must establish:

* immutable incident-generation request and result values
* eligible-anomaly reader contract
* SQLAlchemy eligible-anomaly reader
* deterministic incident-generation service
* explicit batching and temporal-window behavior
* anomaly-to-grouping-input mapping
* grouping and persistence orchestration
* idempotent repeated execution
* safe partial-progress semantics
* focused unit tests
* explicit full-window incident generation orchestration
* eligible unassigned finding traversal by source event time
* guarded PostgreSQL integration tests
* documentation

## Target Flow

```text
IncidentGenerationRequest
        ↓
Read eligible unassigned anomalies
        ↓
Map persisted anomaly rows to IncidentGroupingInput
        ↓
DeterministicIncidentGrouper
        ↓
IncidentCandidate values
        ↓
IncidentPersistence
        ↓
IncidentGenerationResult
```

## Eligibility

Day 14 should read only anomaly findings that:

* are not already assigned to an incident
* fall inside the requested source-event time window
* have valid related log-event context
* are returned in deterministic order

Eligibility must be based on source event time, not anomaly persistence time.

## Runtime Boundary

Day 14 creates an application use case only.

It must not be invoked automatically by:

* ingestion workers
* application startup
* FastAPI routes
* schedulers
* background loops

## Day 14 Boundaries

Do not implement:

* periodic scheduling
* worker integration
* lifecycle integration
* manual API trigger
* acknowledgement
* resolution
* assignment
* comments
* alerting
* notifications
* LLM explanations
* statistical clustering
* Day 15 functionality

## Immediate Next Step

Give Codex the complete Day 14 Incident Generation Orchestration specification.

Do not implement Day 15.
