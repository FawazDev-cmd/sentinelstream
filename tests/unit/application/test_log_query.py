from dataclasses import FrozenInstanceError
from datetime import UTC, datetime
from uuid import UUID

import pytest

from app.application.queries.logs import (
    MAX_LOG_QUERY_LIMIT,
    MIN_LOG_QUERY_LIMIT,
    LogEventCursor,
    LogEventQuery,
)
from app.domain.logs import LogLevel

NOW = datetime(2026, 7, 22, 10, tzinfo=UTC)


def test_default_minimum_and_maximum_limits_are_valid() -> None:
    assert LogEventQuery().limit == 50
    assert LogEventQuery(limit=MIN_LOG_QUERY_LIMIT).limit == 1
    assert LogEventQuery(limit=MAX_LOG_QUERY_LIMIT).limit == 100


@pytest.mark.parametrize("limit", [0, 101])
def test_out_of_range_limit_is_rejected(limit: int) -> None:
    with pytest.raises(ValueError, match="between"):
        LogEventQuery(limit=limit)


@pytest.mark.parametrize("field", ["start_time", "end_time"])
def test_naive_query_time_is_rejected(field: str) -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        LogEventQuery(**{field: datetime(2026, 7, 22)})  # type: ignore[arg-type]


def test_start_after_end_is_rejected() -> None:
    with pytest.raises(ValueError, match="later"):
        LogEventQuery(start_time=NOW, end_time=datetime(2026, 7, 22, 9, tzinfo=UTC))


def test_filters_are_preserved_query_is_immutable_and_times_are_utc() -> None:
    cursor = LogEventCursor(NOW, UUID(int=1))
    query = LogEventQuery(
        service="api",
        environment="test",
        level=LogLevel.ERROR,
        start_time=NOW,
        end_time=NOW,
        cursor=cursor,
    )
    assert (query.service, query.environment, query.level, query.cursor) == (
        "api",
        "test",
        LogLevel.ERROR,
        cursor,
    )
    assert query.start_time is not None and query.start_time.tzinfo is UTC
    with pytest.raises(FrozenInstanceError):
        query.limit = 10  # type: ignore[misc]


def test_cursor_rejects_naive_timestamp() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        LogEventCursor(datetime(2026, 7, 22), UUID(int=1))
