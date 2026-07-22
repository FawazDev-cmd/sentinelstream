# SentinelStream — Current State

## Project

SentinelStream is a production-oriented real-time log intelligence platform that ingests structured logs, detects deterministic anomalies, groups related findings into incidents, persists them transactionally, exposes cursor-paginated APIs, emits safe structured operational telemetry, and now includes containerization and continuous-integration configuration.

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
* Day 15.5 — Runtime generation lookback correction
* Day 16 — Production observability and worker visibility

## Completed and Awaiting Commit

Day 17 — Docker, Docker Compose, and GitHub Actions CI

## Current Verification Baseline

```text
399 passed
10 guarded PostgreSQL integration tests collected
Ruff passed
Formatting passed
mypy passed
Compose configuration validated
No dependency changes
No migration changes
```

## Day 17 Deliverables

Added:

```text
Dockerfile
.dockerignore
compose.yaml
.github/workflows/ci.yml
```

Updated:

```text
.env.example
.gitignore
README.md
.ai/current_state.md
.ai/architecture.md
```

## Container Architecture

The local container topology is:

```text
Docker Compose
├── api
│   ├── FastAPI
│   ├── managed ingestion worker
│   ├── structured JSON logs
│   └── health check
│
└── postgres
    ├── PostgreSQL
    ├── persistent named volume
    └── pg_isready health check
```

The API and worker continue to run inside one process boundary managed by the FastAPI lifespan.

No separate worker container exists.

## Docker Image

The production image uses:

```text
Python 3.13 slim
multi-stage build
uv
locked dependency synchronization
non-root runtime user
```

Dependencies are installed using:

```bash
uv sync --frozen --no-dev
```

The runtime container:

* runs as UID `10001`
* uses an exec-form command
* starts the existing FastAPI application
* does not use reload mode
* preserves operating-system signal handling
* does not embed environment secrets
* includes required Alembic runtime files
* excludes development and test artifacts where possible

The application entry point is:

```text
app.presentation.api.main:app
```

## Docker Ignore Policy

The Docker build context excludes:

* Git metadata
* virtual environments
* Python caches
* pytest caches
* mypy caches
* Ruff caches
* coverage output
* distribution and build output
* tests
* local databases
* editor metadata
* `.env` files
* local secrets

Runtime application and Alembic files remain included.

## Docker Compose

Compose defines:

```text
api
postgres
```

### PostgreSQL

The PostgreSQL service includes:

* environment-driven database values
* a clearly named local database
* a persistent named volume
* `pg_isready` health validation
* localhost-only port publication
* no unrestricted public database binding

### API

The API service includes:

* production Dockerfile build
* dependency on healthy PostgreSQL
* localhost API-port publication
* SentinelStream environment configuration
* PostgreSQL connection through the Compose hostname
* `/health` health check
* structured logs written to stdout
* `unless-stopped` restart behavior
* no source-code bind mount
* no development reload mode

## Migration Strategy

Alembic remains the sole owner of database schema evolution.

Migrations are applied explicitly:

```bash
docker compose run --rm api uv run alembic upgrade head
```

The application does not:

* call `Base.metadata.create_all`
* create tables during startup
* silently suppress migration errors
* mutate schema outside Alembic

Current migration head remains:

```text
20260722_0003
```

## Docker Quick Start

```bash
cp .env.example .env
docker compose build
docker compose up -d postgres
docker compose run --rm api uv run alembic upgrade head
docker compose up -d api
docker compose ps
curl http://localhost:8000/health
```

Shutdown:

```bash
docker compose down
```

Destructive database reset:

```bash
docker compose down -v
```

The `-v` command deletes the local PostgreSQL volume and its data.

## Environment Configuration

`.env.example` provides safe local examples for:

* PostgreSQL database
* PostgreSQL username
* PostgreSQL password
* SentinelStream database URL
* API port
* queue capacity
* structured logging
* runtime incident-generation lookback

Real `.env` variants remain ignored.

No real credentials are included.

## Continuous Integration

GitHub Actions contains separate jobs for:

```text
quality
PostgreSQL integration
Docker build
```

Workflow permissions are read-only.

### Quality Job

The quality job runs:

```bash
uv sync --frozen
uv run ruff check .
uv run ruff format --check .
uv run mypy app tests
uv run pytest -m "not integration"
```

### PostgreSQL Integration Job

The integration job:

* provisions PostgreSQL
* uses the database `sentinelstream_test`
* waits for PostgreSQL health
* configures `SENTINELSTREAM_TEST_DATABASE_URL`
* applies Alembic migrations
* executes the integration suite without skipping

The database name satisfies the project’s test-database safety guard.

### Alembic Validation

CI runs:

```bash
uv run alembic history
uv run alembic heads
```

It also programmatically asserts that exactly one migration head exists.

### Docker Build Job

CI builds the production image using Docker BuildKit.

It does not:

* push an image
* use registry credentials
* publish a release
* deploy to cloud infrastructure

## Local Verification Results

```text
uv run pytest
PASS — 399 passed, 10 skipped
```

```text
uv run pytest -m "not integration"
PASS — 399 passed
```

```text
uv run pytest -m integration -rs
SKIPPED — 10 tests because SENTINELSTREAM_TEST_DATABASE_URL is absent locally
```

```text
uv run ruff check .
PASS
```

```text
uv run ruff format --check .
PASS — 143 Python files formatted
```

```text
uv run mypy app tests
PASS — no issues across 139 source files
```

```text
docker compose config
PASS
```

```text
docker compose config --quiet
PASS
```

```text
git diff --check
PASS
```

## Local Docker Limitation

The Docker CLI and Compose plugin were available.

The Docker Desktop Linux daemon was not running, so the following could not be completed locally:

* production image build
* container startup
* migration execution inside the container
* API health verification
* container-log inspection
* PostgreSQL integration-test execution

No successful local image-build or runtime-health claim is made.

GitHub Actions must provide the missing independent verification after the Day 17 commit is pushed.

## Dependency Status

No changes to:

```text
pyproject.toml
uv.lock
```

## Migration Status

No migration was added or modified.

Current sole Alembic head:

```text
20260722_0003
```

## Scope Confirmation

Day 17 added no:

* Streamlit
* frontend assets
* Kubernetes
* Helm
* Terraform
* cloud deployment
* container-registry publishing
* release workflow
* separate worker container
* Redis
* Kafka
* Celery
* Prometheus
* OpenTelemetry
* authentication
* new API endpoint
* new business rule
* Day 18 functionality

## Approval Status

Day 17 is approved for commit.

Full Day 17 verification remains conditional on a successful GitHub Actions run.

## Immediate Next Step

1. Commit and push Day 17.
2. Inspect all GitHub Actions jobs.
3. Fix any CI, Docker-build, or PostgreSQL integration failure before Day 18.
4. Begin Day 18 only after the workflow is green.
