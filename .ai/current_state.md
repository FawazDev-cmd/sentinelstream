# SentinelStream — Current State

## Project

SentinelStream is a production-oriented real-time log intelligence platform that ingests structured logs, detects deterministic anomalies, groups related findings into incidents, persists them safely, and exposes logs, anomalies, and incidents through read APIs.

## Completed and Committed

* Day 1 — Project foundation
* Day 2 — Domain contracts
* Day 3 — Log ingestion API
* Day 4 — Queue and worker lifecycle
* Day 5 — PostgreSQL persistence
* Day 6 — Alembic migrations
* Day 7 — Log query API
* Day 8 — Deterministic anomaly detection
* Day 9 — Atomic anomaly persistence
* Day 10 — Anomaly query API
* Day 11 — Deterministic incident grouping
* Day 12 — Transactional incident persistence
* Day 13 — Incident query API
* Day 14 — Incident-generation orchestration
* Day 15 — Runtime incident-generation wiring

## Current Verification Baseline

```text
391 passed
9 skipped PostgreSQL integration tests
Ruff passed
Formatting passed
mypy passed
git diff --check passed
```

## Current Task

Day 15.5 — Runtime Incident Window Correction

## Problem

Day 15 invokes incident generation using:

```text
event_time_from = current event timestamp
event_time_to   = current event timestamp
```

This reads unassigned findings in the inclusive configured event-time lookback.

Related anomalies occurring at different times cannot be grouped during normal runtime processing.

Example:

```text
12:00 — payments error
12:04 — payments error
12:08 — payments error
```

The Day 11 adjacent-gap grouping policy may consider these one temporal cluster, but an exact-timestamp query cannot retrieve the three findings together.

## Correction

Runtime generation must use a bounded rolling lookback window ending at the current source-event timestamp.

```text
event_time_to   = current event timestamp
event_time_from = current event timestamp - configured lookback
```

The lookback must:

* be explicitly configured
* use deterministic event time rather than wall-clock time
* be validated as positive and bounded
* remain independent from database page size
* preserve existing grouping and persistence behavior

## Architectural Scope

Day 15.5 changes only:

* runtime incident-generation window construction
* configuration required for the bounded lookback
* focused tests
* relevant documentation

It must not change:

* incident grouping rules
* incident identity
* persistence transactions
* eligible-finding ordering
* assignment exclusion
* incident query APIs
* ingestion API behavior
* worker architecture

## Known MVP Boundary

The rolling window enables multi-event incident formation across nearby event timestamps.

It does not introduce:

* incident extension after creation
* incident merging
* scheduled historical recovery scans
* distributed coordination
* claims or leases
* retries
* incident lifecycle workflows

## Immediate Next Step

Bounded runtime lookback correction implemented and verified.

Do not implement Day 16.
