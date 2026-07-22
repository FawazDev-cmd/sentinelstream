import math

import pytest
from pydantic import ValidationError

from app.shared.config import Settings


@pytest.mark.parametrize("size", [0, -1])
def test_settings_reject_invalid_queue_size(size: int) -> None:
    with pytest.raises(ValidationError):
        Settings(event_queue_max_size=size)


@pytest.mark.parametrize("timeout", [0, -1, math.inf, math.nan])
def test_settings_reject_invalid_shutdown_timeout(timeout: float) -> None:
    with pytest.raises(ValidationError):
        Settings(worker_shutdown_timeout_seconds=timeout)
