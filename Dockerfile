FROM python:3.13-slim AS builder

COPY --from=ghcr.io/astral-sh/uv:0.9.26 /uv /uvx /bin/
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

FROM python:3.13-slim AS runtime

COPY --from=ghcr.io/astral-sh/uv:0.9.26 /uv /uvx /bin/
RUN useradd --create-home --uid 10001 --shell /usr/sbin/nologin sentinelstream
WORKDIR /app
COPY --from=builder --chown=sentinelstream:sentinelstream /app/.venv /app/.venv
COPY --chown=sentinelstream:sentinelstream pyproject.toml uv.lock alembic.ini ./
COPY --chown=sentinelstream:sentinelstream alembic ./alembic
COPY --chown=sentinelstream:sentinelstream app ./app

ENV PATH="/app/.venv/bin:$PATH" PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
USER sentinelstream
EXPOSE 8000
CMD ["uv", "run", "--frozen", "--no-sync", "uvicorn", "app.presentation.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
