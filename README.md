# SentinelStream

SentinelStream is a portfolio-first, real-time log intelligence platform. The repository currently includes the application foundation, log domain contracts, and a non-durable single-event ingestion boundary.

> SentinelStream is under active development. The ingestion endpoint validates and normalizes events but does not queue or persist them. Asynchronous processing, persistence, anomaly detection, incidents, and dashboards are not implemented.

## Architecture principles

- Keep domain logic independent of frameworks and infrastructure.
- Make configuration and application construction explicit and testable.
- Maintain a one-way dependency direction from adapters toward core contracts.
- Add modules only when a milestone needs them.
- Prefer deterministic behavior and evidence-based explanations.

## Approved stack

Python 3.13, uv, FastAPI, Uvicorn, Pydantic, pydantic-settings, standard-library logging, pytest, HTTPX, Ruff, and mypy.

## Setup

Install uv using an official installation method, then install the project:

```bash
uv sync
```

Copy `.env.example` to `.env` if local overrides are needed. Start the development server with:

```bash
uv run uvicorn app.presentation.api.main:app --reload
```

`GET http://127.0.0.1:8000/health` reports process health and configured service identity. `POST http://127.0.0.1:8000/api/v1/logs` validates one structured log and returns a non-durable HTTP 202 acceptance response.

## Quality checks

```bash
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run mypy app tests
```

To apply formatting during development, run `uv run ruff format .`.
