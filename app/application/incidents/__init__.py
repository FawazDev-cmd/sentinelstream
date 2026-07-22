"""Pure deterministic incident grouping behavior."""

from app.application.incidents.contracts import IncidentGrouper
from app.application.incidents.exceptions import (
    IncidentFindingAlreadyAssignedError,
    IncidentPersistenceConflictError,
)
from app.application.incidents.generation import (
    DuplicateEligibleIncidentFindingError,
    EligibleIncidentFinding,
    EligibleIncidentFindingCursor,
    EligibleIncidentFindingPage,
    EligibleIncidentFindingReader,
    GenerateIncidents,
    IncidentGenerationCursorProgressError,
    IncidentGenerationRequest,
    IncidentGenerationResult,
)
from app.application.incidents.grouper import (
    DeterministicIncidentGrouper,
    DuplicateIncidentGroupingFindingError,
)
from app.application.incidents.identity import build_incident_id
from app.application.incidents.models import (
    IncidentGroupingInput,
    IncidentGroupingPolicy,
)
from app.application.incidents.persistence import IncidentPersistence

__all__ = [
    "DeterministicIncidentGrouper",
    "DuplicateEligibleIncidentFindingError",
    "DuplicateIncidentGroupingFindingError",
    "EligibleIncidentFinding",
    "EligibleIncidentFindingCursor",
    "EligibleIncidentFindingPage",
    "EligibleIncidentFindingReader",
    "GenerateIncidents",
    "IncidentFindingAlreadyAssignedError",
    "IncidentGenerationCursorProgressError",
    "IncidentGenerationRequest",
    "IncidentGenerationResult",
    "IncidentGrouper",
    "IncidentGroupingInput",
    "IncidentGroupingPolicy",
    "IncidentPersistence",
    "IncidentPersistenceConflictError",
    "build_incident_id",
]
