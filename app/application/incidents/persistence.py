"""Focused persistence contract for immutable incident candidates."""

from typing import Protocol
from uuid import UUID

from app.domain.incidents import IncidentCandidate


class IncidentPersistence(Protocol):
    async def persist(self, candidate: IncidentCandidate) -> UUID: ...
