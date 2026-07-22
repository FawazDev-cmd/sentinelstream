"""Normalized log-event domain contracts."""

from app.domain.logs.models import LogEvent
from app.domain.logs.types import LogLevel

__all__ = ["LogEvent", "LogLevel"]
