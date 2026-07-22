"""Read-only persisted-incident routes."""

from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.application.contracts.incident_reader import IncidentReader
from app.application.queries.incident_cursor import (
    InvalidIncidentCursorError,
    decode_incident_cursor,
    encode_incident_cursor,
)
from app.application.queries.incidents import (
    DEFAULT_INCIDENT_QUERY_LIMIT,
    MAX_INCIDENT_QUERY_LIMIT,
    MIN_INCIDENT_QUERY_LIMIT,
    IncidentQuery,
)
from app.domain.anomalies import AnomalySeverity, AnomalyType
from app.domain.logs.models import ENVIRONMENT_MAX_LENGTH, SERVICE_MAX_LENGTH
from app.presentation.api.dependencies import get_incident_reader
from app.presentation.api.schemas.incidents import (
    IncidentDetailResponse,
    IncidentPageResponse,
    IncidentResponse,
)

router = APIRouter(prefix="/api/v1", tags=["incidents"])


@router.get("/incidents", response_model=IncidentPageResponse)
async def list_incidents(
    reader: Annotated[IncidentReader, Depends(get_incident_reader)],
    service: Annotated[
        str | None, Query(min_length=1, max_length=SERVICE_MAX_LENGTH)
    ] = None,
    environment: Annotated[
        str | None, Query(min_length=1, max_length=ENVIRONMENT_MAX_LENGTH)
    ] = None,
    anomaly_type: AnomalyType | None = None,
    highest_severity: AnomalySeverity | None = None,
    started_after: datetime | None = None,
    started_before: datetime | None = None,
    last_seen_after: datetime | None = None,
    last_seen_before: datetime | None = None,
    minimum_finding_count: Annotated[int | None, Query(ge=2, le=10_000)] = None,
    limit: Annotated[
        int, Query(ge=MIN_INCIDENT_QUERY_LIMIT, le=MAX_INCIDENT_QUERY_LIMIT)
    ] = DEFAULT_INCIDENT_QUERY_LIMIT,
    cursor: Annotated[str | None, Query(min_length=1)] = None,
) -> IncidentPageResponse:
    try:
        query = IncidentQuery(
            service,
            environment,
            anomaly_type,
            highest_severity,
            started_after,
            started_before,
            last_seen_after,
            last_seen_before,
            minimum_finding_count,
            limit,
            decode_incident_cursor(cursor) if cursor is not None else None,
        )
    except InvalidIncidentCursorError as error:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY, "Invalid incident pagination cursor."
        ) from error
    except (TypeError, ValueError) as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(error)) from error
    try:
        page = await reader.list(query)
    except Exception as error:
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR, "Unable to retrieve incidents."
        ) from error
    return IncidentPageResponse(
        items=[IncidentResponse.from_incident(item) for item in page.items],
        next_cursor=encode_incident_cursor(page.next_cursor)
        if page.next_cursor
        else None,
    )


@router.get("/incidents/{incident_id}", response_model=IncidentDetailResponse)
async def get_incident(
    incident_id: UUID, reader: Annotated[IncidentReader, Depends(get_incident_reader)]
) -> IncidentDetailResponse:
    try:
        detail = await reader.get(incident_id)
    except Exception as error:
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR, "Unable to retrieve incident."
        ) from error
    if detail is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Incident not found.")
    return IncidentDetailResponse.from_detail(detail)
