"""Application-layer contracts."""

from app.application.contracts.clock import Clock, SystemClock
from app.application.contracts.detection_persistence import DetectionPersistence
from app.application.contracts.event_processor import EventProcessor
from app.application.contracts.event_queue import EventQueue
from app.application.contracts.reader import LogEventReader
from app.application.contracts.repository import LogEventRepository

__all__ = [
    "Clock",
    "DetectionPersistence",
    "EventProcessor",
    "EventQueue",
    "LogEventReader",
    "LogEventRepository",
    "SystemClock",
]
