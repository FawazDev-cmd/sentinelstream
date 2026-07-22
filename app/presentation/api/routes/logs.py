"""Log ingestion and persisted-log retrieval routes."""

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.application.contracts.reader import LogEventReader
from app.application.exceptions import EventQueueFullError
from app.application.queries.cursor import (
    InvalidLogEventCursorError,
    decode_log_event_cursor,
    encode_log_event_cursor,
)
from app.application.queries.logs import (
    DEFAULT_LOG_QUERY_LIMIT,
    MAX_LOG_QUERY_LIMIT,
    MIN_LOG_QUERY_LIMIT,
    LogEventQuery,
)
from app.application.services.ingestion import IngestionService, normalize_log_level
from app.domain.logs.models import ENVIRONMENT_MAX_LENGTH, SERVICE_MAX_LENGTH
from app.presentation.api.dependencies import (
    get_ingestion_service,
    get_log_event_reader,
)
from app.presentation.api.schemas.logs import (
    LogEventPageResponse,
    LogEventResponse,
    LogIngestionRequest,
    LogIngestionResponse,
)

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


@router.get("/logs", response_model=LogEventPageResponse)
async def list_logs(
    reader: Annotated[LogEventReader, Depends(get_log_event_reader)],
    service: Annotated[
        str | None, Query(min_length=1, max_length=SERVICE_MAX_LENGTH)
    ] = None,
    environment: Annotated[
        str | None, Query(min_length=1, max_length=ENVIRONMENT_MAX_LENGTH)
    ] = None,
    level: Annotated[str | None, Query(min_length=1, max_length=20)] = None,
    start_time: datetime | None = None,
    end_time: datetime | None = None,
    limit: Annotated[
        int, Query(ge=MIN_LOG_QUERY_LIMIT, le=MAX_LOG_QUERY_LIMIT)
    ] = DEFAULT_LOG_QUERY_LIMIT,
    cursor: Annotated[str | None, Query(min_length=1)] = None,
) -> LogEventPageResponse:
    try:
        decoded_cursor = decode_log_event_cursor(cursor) if cursor is not None else None
        normalized_level = normalize_log_level(level) if level is not None else None
        query = LogEventQuery(
            service=service,
            environment=environment,
            level=normalized_level,
            start_time=start_time,
            end_time=end_time,
            limit=limit,
            cursor=decoded_cursor,
        )
    except InvalidLogEventCursorError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Invalid pagination cursor.",
        ) from error
    except (TypeError, ValueError) as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(error)
        ) from error
    page = await reader.list(query)
    return LogEventPageResponse(
        items=[LogEventResponse.from_event(event) for event in page.items],
        next_cursor=encode_log_event_cursor(page.next_cursor)
        if page.next_cursor is not None
        else None,
    )
