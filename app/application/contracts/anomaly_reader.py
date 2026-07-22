"""Read-side contract for persisted anomaly findings."""

from typing import Protocol

from app.application.queries.anomalies import AnomalyFindingPage, AnomalyFindingQuery


class AnomalyFindingReader(Protocol):
    async def list(self, query: AnomalyFindingQuery) -> AnomalyFindingPage: ...
