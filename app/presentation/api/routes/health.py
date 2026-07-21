"""Process health endpoint."""

from fastapi import APIRouter, Request
from pydantic import BaseModel

from app.shared.config import Settings

router = APIRouter()


class HealthResponse(BaseModel):
    """Public process-health response."""

    status: str
    service: str
    version: str


@router.get("/health", response_model=HealthResponse)
def health(request: Request) -> HealthResponse:
    """Report that the API process is running."""

    settings: Settings = request.app.state.settings
    return HealthResponse(
        status="ok",
        service=settings.application_name,
        version=settings.application_version,
    )
