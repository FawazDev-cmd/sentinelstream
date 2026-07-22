# SentinelStream — Current State

## Current Status

Days 1–11 are complete and committed. Day 12 adds the incident persistence foundation
and remains uncommitted pending review.

## Incident Persistence

Incident candidates receive deterministic UUIDv5 identities from a fixed project
namespace. Canonical identity inputs are service, environment, anomaly type, UTC
occurrence bounds, and ordered finding UUIDs. Severity, rule IDs, persistence time,
evidence, and mutable runtime state do not affect identity.

Revision `20260722_0003` adds `incidents` and `incident_findings`. Incident rows preserve
the grouping key, occurrence range, finding count, highest severity, and persistence
time. Zero-based membership rows preserve ordered finding UUIDs without copying anomaly
details. One finding is globally restricted to one persisted incident.

`SqlAlchemyIncidentPersistence` uses one fresh session and transaction per candidate. It
adds and flushes the incident before adding memberships. Identical repeat persistence
verifies immutable fields and every membership position, then returns the same UUID
without duplicates. Partial or conflicting state raises a focused conflict; database
assignment conflicts roll back the new incident and all memberships.

Deleting an incident cascades its memberships. Deleting an assigned anomaly finding is
restricted. Downgrading 0003 removes only incident tables and preserves log/anomaly
tables.

## Current Boundary

No grouping orchestration, database grouping read, worker/lifespan integration,
scheduler, incident API, acknowledgement, resolution, assignment, alerting,
notification, explanation, LLM integration, or Day 13 functionality exists. The
persistence adapter is constructed explicitly by tests or future wiring only.