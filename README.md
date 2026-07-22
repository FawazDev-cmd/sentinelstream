# SentinelStream

SentinelStream currently validates single log events, queues trusted domain events in a bounded non-durable in-process queue, and asynchronously persists them to PostgreSQL through a managed background worker.

## Semantics and limitations

`POST /api/v1/logs` returns HTTP 202 only after an event enters the in-process queue. It does not confirm persistence or durable recovery. Queue capacity exhaustion returns HTTP 503.

The worker uses SQLAlchemy 2.x asynchronous APIs with asyncpg to persist normalized events. Persistence failures are safely logged and isolated so later events continue, but there is no retry or dead-letter recovery; a failed asynchronous event is currently lost. Process crashes may also lose queued or processing events. There is no anomaly detection, incident generation, or querying API.

## Local PostgreSQL setup

1. Create a local PostgreSQL database and application user.
2. Set `SENTINELSTREAM_DATABASE_URL` using a local URL such as `postgresql+asyncpg://<user>:<password>@localhost:5432/<database>`.
3. Run `uv sync`.
4. Start the API with `uv run uvicorn app.presentation.api.main:app --reload`.
5. Submit one event to `POST http://127.0.0.1:8000/api/v1/logs`.

Missing tables are currently created during owned application startup using SQLAlchemy `create_all`. This is a temporary local-development mechanism, not a production migration strategy. Alembic is not implemented yet and is expected to replace this behavior later.

`GET /health` remains a shallow process-health check and performs no database query.

## Configuration

- `SENTINELSTREAM_EVENT_QUEUE_MAX_SIZE`: maximum events held in memory; default `1000`.
- `SENTINELSTREAM_WORKER_SHUTDOWN_TIMEOUT_SECONDS`: maximum graceful drain duration; default `10`.
- `SENTINELSTREAM_DATABASE_URL`: SQLAlchemy async PostgreSQL URL.
- `SENTINELSTREAM_DATABASE_ECHO`: SQL statement logging; default `false`.

## Tests

The normal suite requires no PostgreSQL server. Optional integration tests require a dedicated database whose name contains `test`:

```bash
set SENTINELSTREAM_TEST_DATABASE_URL=postgresql+asyncpg://<user>:<password>@localhost:5432/sentinelstream_test
uv run pytest -m integration
```

Run the standard checks with:

```bash
uv sync
uv run pytest
uv run pytest -m "not integration"
uv run ruff check .
uv run ruff format --check .
uv run mypy app tests
git diff --check
```
