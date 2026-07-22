"""FastAPI application construction."""

from fastapi import FastAPI

from app.application.contracts.clock import SystemClock
from app.application.services.ingestion import IngestionService
from app.monitoring.logging import configure_logging
from app.presentation.api.routes.health import router as health_router
from app.presentation.api.routes.logs import router as logs_router
from app.shared.config import Settings, get_settings


def create_app(
    settings: Settings | None = None, ingestion_service: IngestionService | None = None
) -> FastAPI:
    """Build and configure a SentinelStream API application."""
    active_settings = settings or get_settings()
    configure_logging(active_settings)
    application = FastAPI(
        title=active_settings.application_name,
        version=active_settings.application_version,
    )
    application.state.settings = active_settings
    application.state.ingestion_service = ingestion_service or IngestionService(
        SystemClock()
    )
    application.include_router(health_router)
    application.include_router(logs_router)
    return application


app = create_app()
