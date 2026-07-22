# SentinelStream — Current State

## Project

SentinelStream is a portfolio-first, real-time log intelligence platform that ingests structured server logs, detects deterministic anomalies, groups related failures into incidents, and produces evidence-based human-readable explanations.

## Current Status

Day 1 — Project Foundation is complete, committed, and pushed.

The project currently provides:

- Python 3.13 project configuration through uv
- FastAPI application factory
- centralized Pydantic settings
- structured JSON logging
- `GET /health`
- pytest coverage
- Ruff linting and formatting
- strict mypy analysis
- initial modular package structure
- project documentation

Implementation now proceeds to Day 2.

## Current Milestone

Phase 1 — Foundation and Contracts

### Active Task

Day 2 — Log Domain Contracts

### Objective

Define the stable, framework-independent internal representation of a normalized server log event.

Day 2 must establish:

- normalized log levels
- immutable or safely structured log-event identifiers
- UTC-aware event timestamps
- service and environment identity
- optional request, trace, exception, latency, and status-code fields
- bounded metadata
- domain validation rules
- deterministic unit tests

These contracts will become the foundation for ingestion, normalization, persistence, detection, and incident grouping.

## Architecture Direction

Day 2 belongs entirely to the domain layer.

The new code must not depend on:

- FastAPI
- Pydantic request schemas
- SQLAlchemy
- PostgreSQL
- queue implementations
- application services
- Streamlit
- LLM providers
- infrastructure-specific code

The domain model represents SentinelStream’s trusted internal log format after external input has been validated and normalized.

API request models, ORM models, and domain models must remain separate.

## Planned Domain Representation

A normalized log event should support:

- `event_id`
- `timestamp`
- `received_at`
- `service`
- `environment`
- `level`
- `message`
- optional `exception_type`
- optional `exception_message`
- optional `latency_ms`
- optional `status_code`
- optional `trace_id`
- optional `request_id`
- optional `host`
- bounded metadata

Not every field is required.

The minimum useful event should identify:

- when the event occurred
- which service produced it
- which environment it belongs to
- its normalized severity
- its message

## Domain Invariants

The implementation must enforce:

- timezone-aware timestamps
- UTC normalization or explicit UTC-only storage
- non-empty service names
- non-empty environment names
- non-empty messages
- normalized finite log-level values
- non-negative latency
- valid HTTP-style status-code bounds when provided
- bounded string lengths
- bounded metadata size and nesting
- no mutable shared default values

The domain layer should reject invalid internal state rather than silently repair it.

External normalization will be implemented on Day 3.

## Log Levels

Use a small normalized enum covering:

- DEBUG
- INFO
- WARNING
- ERROR
- CRITICAL

Do not include provider-specific aliases such as `WARN`, `FATAL`, or lowercase variants in the domain enum.

Those aliases will be translated during ingestion normalization on Day 3.

## Identifier Policy

`event_id` should use a strongly typed UUID value.

The domain model should accept an explicit UUID so tests and future ingestion logic can control identifiers deterministically.

Do not generate unpredictable identifiers deep inside the model unless exposed through a clearly separate factory.

## Metadata Policy

Metadata exists for additional structured context, but detectors must not depend on arbitrary uncontrolled content.

Day 2 should introduce conservative limits for:

- maximum number of keys
- maximum key length
- maximum supported nesting depth
- supported JSON-compatible scalar and collection values

Do not implement a general-purpose serialization framework.

Keep the policy small, understandable, and testable.

## Implementation Preference

Use Pydantic domain models only if they remain framework-independent and provide clear value for validation and immutability.

A standard dataclass plus explicit validation is also acceptable.

The choice must be justified by simplicity, typing quality, and future conversion boundaries.

Do not reuse FastAPI request models as domain models.

## Day 2 Scope

Create only the domain files necessary for normalized log contracts, likely including:

```text
app/domain/
├── __init__.py
└── logs/
    ├── __init__.py
    ├── models.py
    └── types.py