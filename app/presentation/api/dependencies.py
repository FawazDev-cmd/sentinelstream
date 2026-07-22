"""FastAPI dependency providers."""

from fastapi import Request

from app.application.services.ingestion import IngestionService


def get_ingestion_service(request: Request) -> IngestionService:
    service: IngestionService = request.app.state.ingestion_service
    return service
