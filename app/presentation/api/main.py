"""FastAPI application construction."""

from fastapi import FastAPI

from app.monitoring.logging import configure_logging
from app.presentation.api.routes.health import router as health_router
from app.shared.config import Settings, get_settings


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build and configure a SentinelStream API application."""

    active_settings = settings or get_settings()
    configure_logging(active_settings)

    application = FastAPI(
        title=active_settings.application_name,
        version=active_settings.application_version,
    )
    application.state.settings = active_settings
    application.include_router(health_router)
    return application


app = create_app()
