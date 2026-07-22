# SentinelStream — Current State

## Current Status

Days 1–10 are complete and committed. Day 11 adds a pure deterministic in-memory
incident grouping foundation and remains uncommitted pending review.

## Incident Grouping Foundation

`IncidentGroupingInput` combines one immutable persisted anomaly read value with the
source event's service, environment, and occurrence timestamp. It contains no source
message, metadata, exception-message content, or ORM object.

Grouping identity is exactly `(service, environment, anomaly_type)`. Within each
partition, inputs are sorted by source event timestamp, finding persistence timestamp,
and finding UUID. Temporal clusters use adjacent gaps: with the default five-minute
gap, 12:00, 12:04, and 12:08 form one candidate even though the total span is eight
minutes. A gap exactly equal to five minutes remains grouped; a larger gap splits.

The default policy requires two findings. Qualifying clusters become immutable
`IncidentCandidate` values with aligned finding/event/rule tuples, earliest/latest
source-event times, count, and highest severity selected by explicit severity rank.
Final candidate ordering is deterministic. Duplicate persisted finding UUIDs are
rejected before grouping; repeated event UUIDs remain valid.

## Current Boundary

Grouping performs no I/O and uses no clock, database, framework, worker, scheduler, or
network access. Candidates are not persisted and no incident table, migration,
repository, API, acknowledgement, resolution, assignment, alerting, explanation, LLM
integration, or Day 12 functionality exists.