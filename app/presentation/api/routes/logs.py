"""Log-ingestion HTTP route."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from app.application.exceptions import EventQueueFullError
from app.application.services.ingestion import IngestionService
from app.presentation.api.dependencies import get_ingestion_service
from app.presentation.api.schemas.logs import LogIngestionRequest, LogIngestionResponse

router = APIRouter(prefix="/api/v1", tags=["logs"])


@router.post(
    "/logs", response_model=LogIngestionResponse, status_code=status.HTTP_202_ACCEPTED
)
async def ingest_log(
    request: LogIngestionRequest,
    service: Annotated[IngestionService, Depends(get_ingestion_service)],
) -> LogIngestionResponse:
    try:
        result = await service.ingest(request.to_input())
    except EventQueueFullError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Log ingestion capacity is temporarily unavailable.",
        ) from error
    except (TypeError, ValueError) as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(error)
        ) from error
    return LogIngestionResponse(event_id=result.event_id)
