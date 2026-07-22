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

The application-level `Clock` protocol separates server receipt time from wall-clock access. `SystemClock` returns UTC; the service still validates awareness and normalizes any aware clock value to UTC. The Day 3 terminal behavior returns the constructed event onlyâ€”there is no queue or persistence.

## In-process queue and worker lifecycle

Day 4 adds application protocols for trusted-event queueing and asynchronous processing. `InMemoryEventQueue` is an infrastructure adapter over a private bounded `asyncio.Queue`; publication uses `put_nowait` and translates capacity exhaustion into `EventQueueFullError`.

`create_app` constructs one shared queue for `IngestionService` and `EventWorker`. FastAPI lifespan starts one worker task, attempts bounded graceful draining with `queue.join()` during shutdown, then cancels and awaits the worker. Ordinary processor failures are isolated inside the worker and logged using only approved event identifiers. The queue is process-local and non-durable; there are no retries, dead-letter handling, persistence, or multiple production workers.

## PostgreSQL persistence foundation

Day 5 adds a one-method `LogEventRepository` application protocol and `PersistenceEventProcessor`. Infrastructure owns the SQLAlchemy 2.x declarative base, PostgreSQL-specific ORM model, explicit domain mapper, async engine/session construction, transactional repository, and non-destructive schema helper. The domain remains SQLAlchemy-free.

The ORM uses `event_metadata` as its Python attribute because `metadata` is reserved by SQLAlchemy declarative models; the physical PostgreSQL column remains `metadata` and uses JSONB. Frozen domain mappings and tuples are explicitly converted to mutable dictionaries and lists.

When no processor is injected, `create_app` constructs one engine, session factory, repository, and persistence processor. Internally created engines are application-owned and disposed during shutdown even after a drain timeout. Day 6 removed startup `create_all`; operators must apply Alembic migrations before starting the application. An externally injected engine is caller-owned and is not initialized or disposed by the application. Injecting a processor bypasses database runtime construction.

Repository operations open one session per event, commit once, roll back ordinary commit failures, and propagate errors. Duplicate UUIDs remain primary-key failures; there are no upserts, retries, dead-letter recovery, or query methods.


## Alembic migration authority

Day 6 makes version-controlled Alembic revisions authoritative for PostgreSQL schema evolution. The Alembic environment imports the single infrastructure `Base` and explicit ORM model, resolves the database URL through centralized validated settings, and supports offline SQL plus online asyncpg execution with an independently owned migration engine.

The application lifecycle never invokes Alembic or `Base.metadata.create_all`. Missing migrations therefore surface later as asynchronous persistence failures; they are not automatically repaired. Revision `20260722_0001` owns the `log_events` table and six indexes. Its downgrade deliberately removes only those objects and destroys rows in that table.

## Persisted log read boundary

Day 7 adds immutable application query, cursor, and page values plus the narrow `LogEventReader` protocol. Cursor ordering is fixed to `(timestamp DESC, event_id DESC)` and its predicate uses older timestamps or lower UUIDs at the same timestamp. Cursors are strict URL-safe Base64 JSON tokens containing only UTC timestamp and UUID; they are opaque API values but are not encrypted or signed.

`SqlAlchemyLogEventReader` shares the production session factory, creates a fresh session per call, applies exact and inclusive filters, fetches `limit + 1`, and never commits. Infrastructure explicitly maps ORM records back into domain events and allows invalid persisted data to fail visibly. Presentation validates query parameters and maps malformed cursors to HTTP 422.

No migration was added because revision `20260722_0001` already contains the required timestamp, UUID-primary-key, and composite service/timestamp indexes. No total count, offset pagination, arbitrary ordering, full-text search, or metadata search exists.
