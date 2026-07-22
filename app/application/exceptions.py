"""Application-specific failures."""


class EventQueueFullError(Exception):
    """Raised when an event cannot enter the bounded in-process queue."""


class DetectionResultEventMismatchError(Exception):
    """Raised when detector output refers to a different source event."""
