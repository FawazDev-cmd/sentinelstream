"""Safe focused incident persistence failures."""


class IncidentPersistenceConflictError(Exception):
    """Stored incident state does not match its deterministic candidate."""


class IncidentFindingAlreadyAssignedError(Exception):
    """A finding is already assigned to a persisted incident."""
