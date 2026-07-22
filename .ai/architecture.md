# Architecture

## Direction

The planned logical layers are Domain, Application, Infrastructure,
Presentation, Monitoring, and Shared Configuration. Dependencies point inward:
presentation and infrastructure adapt application contracts, while the domain
remains independent of web, persistence, queue, dashboard, and model-provider
frameworks.

Day 1 creates only the layers with concrete responsibilities:

- `app.presentation` owns FastAPI construction and HTTP routes.
- `app.monitoring` owns standard-library logging configuration.
- `app.shared` owns process configuration.

Future layer packages will be added only when a milestone supplies real behavior.

## Application construction

`create_app` accepts optional settings, configures logging, stores the active
settings on application state, and registers the health router. The exported
`app` instance supports Uvicorn without introducing startup hooks.

## Health semantics

`GET /health` proves only that the HTTP process can respond. It reports service
name and version from active settings and intentionally checks no future external
dependencies.

## Ingestion boundary

Day 3 keeps external schemas in presentation and converts them to an application `IngestionInput`. The application `IngestionService` owns explicit provider-level aliases, UUID selection, clock use, UTC normalization, and construction of the domain `LogEvent`. FastAPI resolves the service from application state populated by `create_app`, allowing deterministic injection without global mutable business state.

The application-level `Clock` protocol separates server receipt time from wall-clock access. `SystemClock` returns UTC; the service still validates awareness and normalizes any aware clock value to UTC. The Day 3 terminal behavior returns the constructed event only—there is no queue or persistence.

## In-process queue and worker lifecycle

Day 4 adds application protocols for trusted-event queueing and asynchronous processing. `InMemoryEventQueue` is an infrastructure adapter over a private bounded `asyncio.Queue`; publication uses `put_nowait` and translates capacity exhaustion into `EventQueueFullError`.

`create_app` constructs one shared queue for `IngestionService` and `EventWorker`. FastAPI lifespan starts one worker task, attempts bounded graceful draining with `queue.join()` during shutdown, then cancels and awaits the worker. Ordinary processor failures are isolated inside the worker and logged using only approved event identifiers. The queue is process-local and non-durable; there are no retries, dead-letter handling, persistence, or multiple production workers.
