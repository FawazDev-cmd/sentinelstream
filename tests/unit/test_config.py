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


def test_incident_generation_lookback_default_and_bounds() -> None:
    assert Settings().incident_generation_lookback_seconds == 3600
    assert (
        Settings(
            incident_generation_lookback_seconds=1
        ).incident_generation_lookback_seconds
        == 1
    )
    assert (
        Settings(
            incident_generation_lookback_seconds=86_400
        ).incident_generation_lookback_seconds
        == 86_400
    )
    for invalid in (0, 86_401):
        with pytest.raises(ValidationError):
            Settings(incident_generation_lookback_seconds=invalid)
