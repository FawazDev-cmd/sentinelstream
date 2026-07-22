"""Deterministic boundary matrices for incident temporal clustering."""

from datetime import timedelta

import pytest

from app.application.incidents import (
    DeterministicIncidentGrouper,
    IncidentGroupingPolicy,
)
from tests.unit.application.incidents.test_grouper import grouped_input


@pytest.mark.parametrize("number", range(1, 26))
def test_exact_maximum_gap_is_inclusive_for_many_explicit_ids(number: int) -> None:
    inputs = (grouped_input(number * 10, 0), grouped_input(number * 10 + 1, 5))
    result = DeterministicIncidentGrouper(IncidentGroupingPolicy()).group(inputs)
    assert len(result) == 1 and result[0].finding_count == 2


@pytest.mark.parametrize("seconds", range(1, 26))
def test_custom_subminute_adjacent_gap_boundaries(seconds: int) -> None:
    policy = IncidentGroupingPolicy(maximum_gap=timedelta(seconds=seconds))
    inputs = (
        grouped_input(seconds * 10, 0),
        grouped_input(seconds * 10 + 1, seconds / 60),
    )
    result = DeterministicIncidentGrouper(policy).group(tuple(reversed(inputs)))
    assert len(result) == 1
    assert result[0].finding_ids[0].int == seconds * 10
