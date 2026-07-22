"""Expected application-level failures."""


class EventQueueFullError(Exception):
    """Raised when an event cannot enter the bounded queue immediately."""
