"""Narrow synchronous incident grouping contract."""

from collections.abc import Sequence
from typing import Protocol

from app.application.incidents.models import IncidentGroupingInput
from app.domain.incidents import IncidentCandidate


class IncidentGrouper(Protocol):
    def group(
        self, inputs: Sequence[IncidentGroupingInput]
    ) -> tuple[IncidentCandidate, ...]: ...
