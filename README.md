# SentinelStream

SentinelStream is a portfolio-first, real-time log intelligence platform. The
repository currently contains only the Day 1 application foundation: typed
configuration, structured logging, a FastAPI application factory, and a health
endpoint.

> SentinelStream is under active development. Log ingestion, persistence,
> anomaly detection, incident grouping, explanations, operational metrics,
> simulation, and a dashboard are planned capabilities, not implemented ones.

## Architecture principles

- Keep domain logic independent of frameworks and infrastructure.
- Make configuration and application construction explicit and testable.
- Maintain a one-way dependency direction from adapters toward core contracts.
- Add modules only when a milestone needs them.
- Prefer deterministic behavior and evidence-based explanations.

The Day 1 package includes only the presentation, monitoring, and shared
configuration foundations. Future milestones are planned to introduce domain,
application, and infrastructure layers as their behavior becomes concrete.

## Approved stack

Python 3.13, uv, FastAPI, Uvicorn, Pydantic, pydantic-settings, standard-library
logging, pytest, HTTPX, Ruff, and mypy.

## Setup

Install uv using an official installation method, then install the project:

```bash
uv sync
```

Copy `.env.example` to `.env` if local overrides are needed. Start the
development server with:

```bash
uv run uvicorn app.presentation.api.main:app --reload
```

`GET http://127.0.0.1:8000/health` reports process health and configured service
identity only.

## Quality checks

```bash
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run mypy app tests
```

To apply formatting during development, run `uv run ruff format .`.
