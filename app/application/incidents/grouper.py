"""Pure deterministic adjacent-gap incident grouping."""

from collections import defaultdict
from collections.abc import Sequence

from app.application.incidents.models import (
    IncidentGroupingInput,
    IncidentGroupingPolicy,
)
from app.domain.incidents import IncidentCandidate, IncidentGroupingKey


class DuplicateIncidentGroupingFindingError(ValueError):
    def __init__(self, finding_id: object) -> None:
        super().__init__(f"duplicate incident grouping finding_id={finding_id}")


class DeterministicIncidentGrouper:
    def __init__(self, policy: IncidentGroupingPolicy) -> None:
        self._policy = policy

    def group(
        self, inputs: Sequence[IncidentGroupingInput]
    ) -> tuple[IncidentCandidate, ...]:
        values = tuple(inputs)
        seen: set[object] = set()
        for value in values:
            finding_id = value.finding.id
            if finding_id in seen:
                raise DuplicateIncidentGroupingFindingError(finding_id)
            seen.add(finding_id)
        partitions: dict[IncidentGroupingKey, list[IncidentGroupingInput]] = (
            defaultdict(list)
        )
        for value in values:
            key = IncidentGroupingKey(
                value.service, value.environment, value.finding.anomaly_type
            )
            partitions[key].append(value)
        candidates: list[IncidentCandidate] = []
        for key, partition in partitions.items():
            ordered = sorted(
                partition,
                key=lambda item: (
                    item.event_timestamp,
                    item.finding.created_at,
                    item.finding.id,
                ),
            )
            cluster: list[IncidentGroupingInput] = []
            for value in ordered:
                if (
                    cluster
                    and value.event_timestamp - cluster[-1].event_timestamp
                    > self._policy.maximum_gap
                ):
                    self._append_candidate(candidates, key, cluster)
                    cluster = []
                cluster.append(value)
            self._append_candidate(candidates, key, cluster)
        candidates.sort(
            key=lambda item: (
                item.started_at,
                item.last_seen_at,
                item.key.service,
                item.key.environment,
                item.key.anomaly_type.value,
                item.finding_ids[0],
            )
        )
        return tuple(candidates)

    def _append_candidate(
        self,
        candidates: list[IncidentCandidate],
        key: IncidentGroupingKey,
        cluster: list[IncidentGroupingInput],
    ) -> None:
        if len(cluster) < self._policy.minimum_findings:
            return
        candidates.append(
            IncidentCandidate(
                key=key,
                finding_ids=tuple(value.finding.id for value in cluster),
                event_ids=tuple(value.finding.event_id for value in cluster),
                rule_ids=tuple(value.finding.rule_id for value in cluster),
                started_at=cluster[0].event_timestamp,
                last_seen_at=cluster[-1].event_timestamp,
                finding_count=len(cluster),
                highest_severity=max(
                    (value.finding.severity for value in cluster),
                    key=lambda severity: severity.rank,
                ),
            )
        )
