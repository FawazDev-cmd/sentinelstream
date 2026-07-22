"""Read-only persisted-anomaly query route."""

from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.application.contracts.anomaly_reader import AnomalyFindingReader
from app.application.queries.anomalies import (
    DEFAULT_ANOMALY_QUERY_LIMIT,
    MAX_ANOMALY_QUERY_LIMIT,
    MIN_ANOMALY_QUERY_LIMIT,
    AnomalyFindingQuery,
)
from app.application.queries.anomaly_cursor import (
    InvalidAnomalyFindingCursorError,
    decode_anomaly_finding_cursor,
    encode_anomaly_finding_cursor,
)
from app.domain.anomalies import AnomalySeverity, AnomalyType
from app.domain.anomalies.models import RULE_ID_MAX_LENGTH
from app.presentation.api.dependencies import get_anomaly_finding_reader
from app.presentation.api.schemas.anomalies import (
    AnomalyFindingPageResponse,
    AnomalyFindingResponse,
)

router = APIRouter(prefix="/api/v1", tags=["anomalies"])


@router.get("/anomalies", response_model=AnomalyFindingPageResponse)
async def list_anomalies(
    reader: Annotated[AnomalyFindingReader, Depends(get_anomaly_finding_reader)],
    event_id: UUID | None = None,
    anomaly_type: AnomalyType | None = None,
    severity: AnomalySeverity | None = None,
    rule_id: Annotated[
        str | None, Query(min_length=1, max_length=RULE_ID_MAX_LENGTH)
    ] = None,
    start_time: datetime | None = None,
    end_time: datetime | None = None,
    limit: Annotated[
        int, Query(ge=MIN_ANOMALY_QUERY_LIMIT, le=MAX_ANOMALY_QUERY_LIMIT)
    ] = DEFAULT_ANOMALY_QUERY_LIMIT,
    cursor: Annotated[str | None, Query(min_length=1)] = None,
) -> AnomalyFindingPageResponse:
    try:
        decoded_cursor = (
            decode_anomaly_finding_cursor(cursor) if cursor is not None else None
        )
        query = AnomalyFindingQuery(
            event_id=event_id,
            anomaly_type=anomaly_type,
            severity=severity,
            rule_id=rule_id,
            start_time=start_time,
            end_time=end_time,
            limit=limit,
            cursor=decoded_cursor,
        )
    except InvalidAnomalyFindingCursorError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Invalid anomaly pagination cursor.",
        ) from error
    except (TypeError, ValueError) as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(error)
        ) from error
    try:
        page = await reader.list(query)
    except Exception as error:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to retrieve anomaly findings.",
        ) from error
    return AnomalyFindingPageResponse(
        items=[AnomalyFindingResponse.from_finding(item) for item in page.items],
        next_cursor=(
            encode_anomaly_finding_cursor(page.next_cursor)
            if page.next_cursor is not None
            else None
        ),
    )
