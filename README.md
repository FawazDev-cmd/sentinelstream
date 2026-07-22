# SentinelStream

SentinelStream is a portfolio-first log intelligence project. It currently exposes validated single-event ingestion backed by a bounded in-process asynchronous queue and one managed background worker.

## Current ingestion semantics

`POST /api/v1/logs` validates and normalizes a structured log into the trusted domain model. HTTP 202 means the event was successfully placed into the in-process queue. Publication is non-blocking; when capacity is exhausted, the endpoint returns HTTP 503.

The background worker sends queued events to an asynchronous processor. Processor failures are safely logged and isolated so later events can continue. Shutdown attempts to drain queued work for a bounded period before cancelling and awaiting the worker.

This queue is not durable or distributed. Queued or processing events may be lost if the process crashes or is forcibly terminated. There is no persistence, anomaly detection, incident generation, retry, or dead-letter behavior.

`GET /health` reports process health and configured service identity only.

## Configuration

- `SENTINELSTREAM_EVENT_QUEUE_MAX_SIZE` controls the maximum events held in memory; default `1000`.
- `SENTINELSTREAM_WORKER_SHUTDOWN_TIMEOUT_SECONDS` controls the maximum graceful shutdown drain duration; default `10`.

## Setup

```bash
uv sync
uv run uvicorn app.presentation.api.main:app --reload
```

## Quality checks

```bash
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run mypy app tests
git diff --check
```
