# SentinelStream

SentinelStream validates single log events, places trusted events into a bounded non-durable in-process queue, and asynchronously persists them to PostgreSQL through SQLAlchemy and asyncpg.

## Persistence and delivery semantics

`POST /api/v1/logs` returns HTTP 202 after queue placement only. It does not confirm persistence. The queue is process-local and non-durable, and process crashes may lose queued or processing events.

Persistence failures are safely isolated by the worker, but there is no retry or dead-letter recovery. If the database schema has not been migrated, queued events can fail asynchronously and be lost after the failure is logged.

## PostgreSQL and migrations

Create the PostgreSQL database and user, then configure:

```text
SENTINELSTREAM_DATABASE_URL=postgresql+asyncpg://<user>:<password>@localhost:5432/<database>
```

Install dependencies and apply all migrations before starting the API:

```bash
uv sync
uv run alembic upgrade head
uv run uvicorn app.presentation.api.main:app --host 127.0.0.1 --port 8000
```

Alembic is authoritative for schema management. Application startup does not create tables, inspect migration history, or apply migrations automatically.

Useful commands:

```bash
uv run alembic current
uv run alembic history
uv run alembic heads
uv run alembic revision --autogenerate -m "describe schema change"
uv run alembic downgrade -1
```

Review generated migrations before applying them. Downgrades can delete schema objects and data; the initial downgrade removes `log_events` and all rows in it.

`GET /health` remains a shallow process-health check and performs no database query.

## Tests and quality checks

The normal suite requires no PostgreSQL server. Migration integration tests require `SENTINELSTREAM_TEST_DATABASE_URL` and refuse destructive downgrade testing unless the database name contains `test`.

```bash
uv run pytest
uv run pytest -m "not integration"
uv run pytest -m integration -rs
uv run ruff check .
uv run ruff format --check .
uv run mypy app tests
git diff --check
```
