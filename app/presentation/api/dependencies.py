"""FastAPI dependency providers."""

from fastapi import Request

from app.application.contracts.reader import LogEventReader
from app.application.services.ingestion import IngestionService


def get_ingestion_service(request: Request) -> IngestionService:
    service: IngestionService = request.app.state.ingestion_service
    return service


def get_log_event_reader(request: Request) -> LogEventReader:
    reader: LogEventReader | None = request.app.state.log_event_reader
    if reader is None:
        raise RuntimeError("log event reader is not configured")
    return reader
