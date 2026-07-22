# SentinelStream

SentinelStream validates single log events, queues them in a bounded non-durable in-process queue, asynchronously persists them to PostgreSQL, and provides cursor-paginated retrieval.

## Setup and migrations

Configure `SENTINELSTREAM_DATABASE_URL`, then run:

```bash
uv sync
uv run alembic upgrade head
uv run uvicorn app.presentation.api.main:app --host 127.0.0.1 --port 8000
```

Alembic migrations are explicit operator actions. Application startup does not create or migrate tables. HTTP 202 from `POST /api/v1/logs` means queue placement only, not persistence.

## Query persisted logs

Unfiltered:

```bash
curl "http://127.0.0.1:8000/api/v1/logs"
```

Exact service and normalized level filters:

```bash
curl "http://127.0.0.1:8000/api/v1/logs?service=payments-api&level=error&limit=25"
```

Inclusive time range:

```bash
curl "http://127.0.0.1:8000/api/v1/logs?start_time=2026-07-22T00:00:00Z&end_time=2026-07-22T23:59:59Z"
```

Next page:

```bash
curl "http://127.0.0.1:8000/api/v1/logs?limit=25&cursor=<next_cursor>"
```

URL-encode cursor values when necessary. Results are always newest first by event timestamp and UUID. The default limit is 50 and maximum is 100. Cursors are encoded opaque tokens, not encrypted or signed. Responses intentionally contain no total count.

Supported filters are exact `service`, `environment`, and `level`, with inclusive event-time bounds. There is no partial matching, full-text search, metadata search, aggregation, arbitrary sorting, or offset pagination.

Migrations must be applied before persistence and retrieval. The queue remains process-local and non-durable; persistence failures have no retry or dead-letter recovery.

## Quality checks

```bash
uv run pytest
uv run pytest -m "not integration"
uv run pytest -m integration -rs
uv run ruff check .
uv run ruff format --check .
uv run mypy app tests
git diff --check
```
