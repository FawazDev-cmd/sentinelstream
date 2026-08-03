SentinelStream — Current State

Project

SentinelStream is a portfolio-first real-time log intelligence platform that ingests structured server logs, detects deterministic anomalies, groups related failures into incidents, persists all operational data in PostgreSQL, and exposes the system through REST APIs and a lightweight Streamlit dashboard.

MVP Status

SentinelStream MVP v1 is complete.

All planned development milestones from Day 1 through Day 18 have been implemented and verified within the available environment.

Completed Milestones

- Day 1 — Project Foundation
- Day 2 — Log Domain Contracts
- Day 3 — Log Ingestion API
- Day 4 — Asynchronous Queue and Worker Lifecycle
- Day 5 — PostgreSQL Persistence Foundation
- Day 6 — Alembic Migration Foundation
- Day 7 — Log Query API and Cursor Pagination
- Day 8 — Deterministic Anomaly Rules Engine
- Day 9 — Atomic Anomaly Persistence and Worker Integration
- Day 10 — Anomaly Query API and Cursor Pagination
- Day 11 — Deterministic Incident Grouping
- Day 12 — Transactional Incident Persistence
- Day 13 — Incident Query API and Cursor Pagination
- Day 14 — Incident Generation Orchestration
- Day 15 — Runtime Incident Generation Integration
- Day 15.5 — Runtime Generation Lookback Correction
- Day 16 — Production Observability and Worker Visibility
- Day 17 — Docker, Docker Compose, and GitHub Actions CI
- Day 18 — Streamlit Demo Dashboard and Repository Polish

Core Runtime Flow

Structured log request
        ↓
FastAPI ingestion endpoint
        ↓
Bounded asynchronous queue
        ↓
Managed background worker
        ↓
Deterministic anomaly detection
        ↓
Atomic log and anomaly persistence
        ↓
Rolling event-time incident generation
        ↓
Deterministic incident grouping
        ↓
Transactional incident persistence
        ↓
REST APIs and Streamlit dashboard

Backend Capabilities

SentinelStream provides:

- structured JSON log ingestion;
- strict request validation and normalization;
- immutable domain values;
- bounded in-process asynchronous processing;
- PostgreSQL persistence;
- explicit Alembic migrations;
- deterministic anomaly detection;
- error-level detection;
- server-error status detection;
- exception-presence detection;
- latency anomaly detection;
- immutable anomaly findings;
- atomic event-and-finding persistence;
- deterministic incident grouping;
- adjacent-gap temporal clustering;
- configurable runtime incident lookback;
- deterministic UUIDv5 incident identity;
- ordered anomaly-to-incident memberships;
- idempotent incident persistence;
- database-enforced assignment uniqueness;
- stable keyset pagination;
- exact filtering;
- structured lifecycle observability;
- safe failure classification;
- monotonic processing-duration measurement;
- managed worker startup and shutdown.

Public REST APIs

GET  /health
POST /api/v1/logs
GET  /api/v1/logs
GET  /api/v1/anomalies
GET  /api/v1/incidents
GET  /api/v1/incidents/{incident_id}

Streamlit Dashboard

The Streamlit frontend is isolated under:

streamlit_app/

It communicates with SentinelStream exclusively through the existing REST APIs.

It does not access PostgreSQL directly and does not duplicate backend business logic.

Pages

- Overview
- Logs
- Anomalies
- Incidents
- Demo
- About

Overview

Displays:

- backend availability;
- API health;
- project summary;
- log, anomaly, and incident information available through the APIs.

Logs

Provides:

- server-side cursor pagination;
- service filtering;
- environment filtering;
- level filtering;
- manual refresh.

Anomalies

Provides:

- anomaly listing;
- severity information;
- anomaly type;
- stable rule IDs;
- safe evidence;
- API-supported filtering.

Incidents

Provides:

- incident summaries;
- severity;
- service;
- finding counts;
- first-seen and last-seen times;
- incident detail loading;
- ordered anomaly memberships.

Demo

Provides a form for submitting a sample log through:

POST /api/v1/logs

The interface explains that HTTP 202 represents queue acceptance and that anomaly and incident processing occur asynchronously.

It does not poll continuously.

About

Documents:

- project purpose;
- system architecture;
- technology choices;
- Clean Architecture boundaries;
- deterministic processing design;
- current MVP limitations.

Streamlit Configuration

The frontend uses:

STREAMLIT_BACKEND_URL

Local default:

http://127.0.0.1:8000

Docker Compose value:

http://api:8000

Streamlit Container

Added:

Dockerfile.streamlit

The frontend container remains separate from the backend API container.

The dashboard communicates with the API through the Compose service network.

Error Handling

The Streamlit client handles:

- backend unavailability;
- connection failures;
- request timeouts;
- malformed responses;
- unsuccessful API responses.

The interface displays safe user-facing messages.

It does not expose stack traces, credentials, database URLs, or internal backend exceptions.

Dependencies

Day 18 added only:

streamlit
requests

"pyproject.toml" was repaired after malformed literal line-ending markers were introduced.

The file was validated as proper TOML, and "uv.lock" was regenerated successfully.

No unnecessary frontend framework or state-management dependencies were added.

Docker Architecture

Docker Compose
├── api
│   ├── FastAPI
│   ├── managed ingestion worker
│   └── structured JSON logs
│
├── dashboard
│   └── REST-only demonstration dashboard
│
└── postgres
    ├── PostgreSQL
    └── persistent named volume

Alembic remains the sole owner of schema evolution.

The application does not create tables automatically during startup.

Continuous Integration

GitHub Actions configuration includes:

- locked dependency synchronization;
- Ruff linting;
- Ruff formatting checks;
- strict mypy;
- non-integration tests;
- PostgreSQL integration tests;
- Alembic migration validation;
- single-head migration assertion;
- production Docker image build.

The workflow does not publish images or perform cloud deployment.

Documentation

The repository now includes:

- recruiter-focused README hero;
- feature summary;
- Mermaid architecture diagram;
- Python quick start;
- Docker quick start;
- Streamlit quick start;
- API overview;
- testing details;
- design principles;
- limitations and future work;
- screenshot capture plan;
- demo walkthrough.

The recruiter demo guide is located at:

docs/demo.md

It covers:

1. starting PostgreSQL;
2. applying migrations;
3. starting the API;
4. starting Streamlit;
5. submitting sample logs;
6. observing anomalies;
7. observing incidents;
8. reviewing structured processing logs.

Verification Results

uv run pytest
PASS — 406 passed, 10 skipped

The skipped tests require:

SENTINELSTREAM_TEST_DATABASE_URL

Frontend boundary tests
PASS — 7 new tests

uv run ruff check .
PASS

uv run ruff format --check .
PASS — 148 files formatted

uv run mypy app tests
PASS — no issues across 141 source files

git diff --check
PASS

Streamlit Verification

The Streamlit application started successfully.

Its health endpoint returned:

HTTP 200

This confirms that:

- dependency installation succeeded;
- the application entry point imports correctly;
- Streamlit can start in the current environment.

Compose Verification

docker compose config
PASS

Full container execution was not available because the Docker Desktop Linux daemon was not running.

Therefore, the following were not claimed as locally verified:

- image build;
- API container startup;
- Streamlit-to-containerized-API communication;
- containerized PostgreSQL migration execution;
- complete Docker demonstration flow.

These should be verified through GitHub Actions and later local Docker execution.

Dependency Status

"pyproject.toml" and "uv.lock" now contain the intended Streamlit dependencies and valid locked resolution.

No backend runtime dependency was changed unnecessarily.

Migration Status

No migration was added or modified during Day 18.

Current Alembic chain:

20260722_0001
        ↓
20260722_0002
        ↓
20260722_0003

Current migration head:

20260722_0003

Architecture Boundaries

The Streamlit frontend:

- uses REST APIs only;
- does not import backend application services;
- does not import ORM models;
- does not open database sessions;
- does not perform anomaly detection;
- does not group incidents;
- does not reproduce persistence logic.

The backend remains the primary engineering artifact.

Current MVP Limitations

SentinelStream intentionally does not yet include:

- authentication;
- authorization;
- multi-tenancy;
- incident acknowledgement;
- incident resolution;
- assignments;
- comments;
- alert notifications;
- durable message brokers;
- retry queues;
- dead-letter queues;
- scheduled recovery scans;
- Prometheus;
- OpenTelemetry;
- distributed tracing;
- Elasticsearch;
- Kafka;
- Kubernetes;
- cloud deployment;
- LLM-generated incident explanations.

These remain future roadmap items rather than MVP requirements.

Final MVP Verification

SentinelStream currently has:

406 passing tests
10 guarded PostgreSQL tests
Ruff passing
Formatting passing
Strict mypy passing
Streamlit startup verified
Streamlit health HTTP 200
Compose configuration valid
No migration drift
No uncommitted backend production-code changes

Commit Decision

Day 18 is complete and approved for commit.

Immediate Next Steps

1. Commit and push Day 18.
2. Confirm the GitHub Actions workflow is fully green.
3. Run the complete Docker Compose flow when Docker Desktop is available.
4. Capture final dashboard screenshots.
5. Record the demo video.
6. Add SentinelStream to the portfolio website.
7. Prepare the SentinelStream project defence and interview cheat sheet.
