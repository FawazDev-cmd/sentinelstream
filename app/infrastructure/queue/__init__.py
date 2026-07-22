"""In-process event queue implementation."""

from app.infrastructure.queue.memory import InMemoryEventQueue

__all__ = ["InMemoryEventQueue"]
