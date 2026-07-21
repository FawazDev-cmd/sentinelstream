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
