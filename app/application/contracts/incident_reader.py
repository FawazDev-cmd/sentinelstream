"""Read-only incident query boundary."""

from typing import Protocol
from uuid import UUID

from app.application.queries.incidents import (
    IncidentPage,
    IncidentQuery,
    PersistedIncidentDetail,
)


class IncidentReader(Protocol):
    async def list(self, query: IncidentQuery) -> IncidentPage: ...

    async def get(self, incident_id: UUID) -> PersistedIncidentDetail | None: ...
