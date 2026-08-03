# SentinelStream demo walkthrough

This walkthrough demonstrates the complete MVP without accessing PostgreSQL directly.
The dashboard communicates only with the public REST API.

## 1. Start Docker

```bash
cp .env.example .env
docker compose build
docker compose up -d postgres
```

Wait until PostgreSQL reports healthy with `docker compose ps`.

## 2. Apply migrations

```bash
docker compose run --rm api uv run alembic upgrade head
```

Revision `20260722_0003` is the expected migration head. Migrations are an explicit
operator action and never run during API startup.

## 3. Start the API

```bash
docker compose up -d api
curl http://localhost:8000/health
```

The API response proves process health. Then inspect `docker compose logs api` to show
structured worker-start telemetry.

## 4. Start Streamlit

```bash
docker compose up -d dashboard
```

Open <http://localhost:8501>. The Compose dashboard uses
`STREAMLIT_BACKEND_URL=http://api:8000`; host execution defaults to
`http://127.0.0.1:8000`.

## 5. Submit sample logs

On **Demo**, submit two error logs with the same service and environment within five
minutes. HTTP 202 confirms bounded queue acceptance, not completed processing.

## 6. Observe anomalies

Open **Anomalies** and choose **Refresh anomalies**. Explain that rules are deterministic
and evidence excludes message contents and metadata.

## 7. Observe an incident

Open **Incidents**, refresh, and select the resulting incident. Show its stable identity,
severity, occurrence bounds, and ordered findings. Two related findings are required by
the default grouping policy.

## 8. Review structured logs

```bash
docker compose logs --no-color api
```

Point out the stable processing ID, ordered lifecycle stages, anomaly/incident counts,
monotonic duration, safe failure classification, and worker lifecycle records. There is
no polling, scheduler, retry loop, or sensitive raw payload logging.

## Host-only alternative

```bash
uv sync
uv run alembic upgrade head
uv run uvicorn app.presentation.api.main:app --host 127.0.0.1 --port 8000
uv run streamlit run streamlit_app/app.py
```
