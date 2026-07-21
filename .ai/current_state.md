# SentinelStream — Current State

## Project

SentinelStream is a portfolio-first, real-time log intelligence platform that ingests structured server logs, detects deterministic anomalies, groups related failures into incidents, and produces evidence-based human-readable explanations.

## Current Status

Repository and local project setup are complete.

The GitHub repository, local workspace, Git initialization, `main` branch, remote connection, and initial commit have been established.

Day 1 is complete. The application foundation and all documented quality gates, including the HTTP smoke test, have been verified.

## Current Milestone

Phase 1 — Foundation and Contracts

### Active Task

Day 1 — Project Foundation

### Objective

Create the smallest verified SentinelStream application foundation using the agreed stack and engineering conventions.

The completed foundation must provide:

- Python 3.13 project configuration through uv
- FastAPI application factory
- central Pydantic settings
- structured JSON logging
- GET /health endpoint
- pytest coverage
- Ruff linting and formatting
- strict mypy analysis
- initial modular package structure
- initial project documentation

## Architecture Direction

The project will use these logical layers:

- Domain
- Application
- Infrastructure
- Presentation
- Monitoring
- Shared configuration

Dependency direction:

- Presentation may depend on application contracts.
- Infrastructure may implement application contracts.
- Application may depend on domain models and policies.
- Domain must remain independent of FastAPI, SQLAlchemy, Streamlit, PostgreSQL, queue implementations, and LLM providers.

Only the presentation, monitoring, and shared configuration foundations are required for Day 1.

## Planned MVP Processing Flow

1. A server or simulator sends a structured JSON log.
2. FastAPI validates the external request.
3. The application normalizes it into a domain LogEvent.
4. The event enters a bounded asynchronous queue.
5. A background processor consumes it.
6. PostgreSQL stores the normalized event.
7. Deterministic detectors evaluate rolling-window evidence.
8. Anomalies are persisted.
9. Related anomalies are grouped into incidents.
10. A deterministic explainer generates an evidence-based explanation.
11. Incident and metrics APIs expose the result.
12. A minimal Streamlit dashboard consumes those APIs.

Only the application foundation is being implemented now.

## Approved Core Stack

- Python 3.13
- uv
- FastAPI
- Uvicorn
- Pydantic
- pydantic-settings
- pytest
- Ruff
- mypy
- standard-library structured JSON logging

Later milestones will add:

- PostgreSQL
- Docker
- GitHub Actions
- Streamlit

## Key Decisions

### Application creation

SentinelStream will use a FastAPI application factory.

This keeps application construction explicit and testable and allows tests to inject custom settings.

### Configuration

Configuration will be centralized using `pydantic-settings`.

Environment variables will use the `SENTINELSTREAM_` prefix.

### Logging

Day 1 will use standard-library logging with a small JSON formatter.

The logging setup must:

- use UTC timestamps
- include level, logger, and message
- include exception information when present
- avoid duplicate handlers
- avoid serializing arbitrary objects

### Health endpoint

`GET /health` will confirm only that the application process is running.

It will not check PostgreSQL, queues, detectors, or external services because those dependencies do not exist yet.

## Day 1 Scope

Create:

- `pyproject.toml`
- `uv.lock`
- `.env.example`
- updated `.gitignore`
- application package
- shared settings module
- monitoring logging module
- FastAPI application factory
- health router
- tests
- initial README updates
- initial `.ai` architecture and development documents

## Day 1 Non-Goals

Do not implement:

- log ingestion
- LogEvent domain models
- asynchronous queues
- workers
- PostgreSQL
- SQLAlchemy
- migrations
- repositories
- anomaly detection
- rolling windows
- incident grouping
- explanations
- LLM integration
- operational metrics
- simulator
- Streamlit
- Docker
- CI

## Quality Gates

Day 1 must pass:

```bash
uv sync
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run mypy app tests
```