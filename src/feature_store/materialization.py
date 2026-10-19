"""Materialization: moving latest values from offline to online.

Materialization is the batch bridge between the two stores. For a given
cutoff time it computes, per entity, the latest offline record at-or-
before the cutoff — the same as-of rule the training join uses, applied
at "now" — and upserts it into the online store. Because both paths use
the same rule over the same history, what a model trains on and what it
is served cannot silently diverge.

Materialization is idempotent: re-running it with the same cutoff
writes nothing new (the online store rejects older-or-equal churn via
its freshness rule and identical timestamps compare equal).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from .offline_store import OfflineStore
from .online_store import OnlineStore
from .registry import FeatureRegistry


@dataclass
class MaterializationResult:
    view_name: str
    cutoff: datetime
    entities_considered: int = 0
    rows_written: int = 0
    rows_skipped_stale: int = 0
    per_view: dict[str, int] = field(default_factory=dict)


class Materializer:
    def __init__(
        self,
        registry: FeatureRegistry,
        offline: OfflineStore,
        online: OnlineStore,
    ) -> None:
        self._registry = registry
        self._offline = offline
        self._online = online

    def materialize_view(self, view_name: str, cutoff: datetime) -> MaterializationResult:
        view = self._registry.get_view(view_name)
        result = MaterializationResult(view_name=view_name, cutoff=cutoff)
        for entity_id in self._offline.entity_ids(view_name):
            result.entities_considered += 1
            records = self._offline.records_for(view_name, entity_id)
            eligible = [r for r in records if r.event_timestamp <= cutoff]
            if not eligible:
                result.rows_skipped_stale += 1
                continue
            latest = eligible[-1]  # records_for returns as-of order
            if self._online.upsert(view, entity_id, latest.values, latest.event_timestamp):
                result.rows_written += 1
            else:
                # Online already holds a newer row (e.g. a fresher batch
                # landed first) — never overwrite it with older history.
                result.rows_skipped_stale += 1
        result.per_view[view_name] = result.rows_written
        return result

    def materialize(
        self, view_names: list[str] | None, cutoff: datetime
    ) -> list[MaterializationResult]:
        names = view_names or [v.name for v in self._registry.list_views()]
        return [self.materialize_view(name, cutoff) for name in names]
