"""Offline/online parity checks.

Training/serving skew often arrives quietly: materialization lags, a
batch is dropped, someone writes the online store directly. The parity
check is the alarm — for every entity in the online store it recomputes
what the offline store says the latest value at the check time should
be, and reports every field that disagrees.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from .offline_store import OfflineStore
from .online_store import OnlineStore
from .registry import FeatureRegistry


@dataclass
class FieldMismatch:
    view_name: str
    entity_id: str
    feature: str
    online_value: Any
    offline_value: Any


@dataclass
class ParityReport:
    view_name: str
    checked_at: datetime
    entities_checked: int = 0
    mismatches: list[FieldMismatch] = field(default_factory=list)
    missing_online: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.mismatches and not self.missing_online

    def summary(self) -> str:
        status = "OK" if self.ok else "MISMATCH"
        return (
            f"[{status}] {self.view_name}: {self.entities_checked} entities checked, "
            f"{len(self.mismatches)} field mismatches, "
            f"{len(self.missing_online)} entities missing online"
        )


class ConsistencyChecker:
    def __init__(
        self,
        registry: FeatureRegistry,
        offline: OfflineStore,
        online: OnlineStore,
    ) -> None:
        self._registry = registry
        self._offline = offline
        self._online = online

    def check_view(self, view_name: str, at: datetime) -> ParityReport:
        view = self._registry.get_view(view_name)
        report = ParityReport(view_name=view_name, checked_at=at)

        offline_latest: dict[str, dict[str, Any]] = {}
        for entity_id in self._offline.entity_ids(view_name):
            records = [
                r
                for r in self._offline.records_for(view_name, entity_id)
                if r.event_timestamp <= at
            ]
            if records:
                offline_latest[entity_id] = records[-1].values

        online_ids = set(self._online.entity_ids(view_name))
        for entity_id, expected in sorted(offline_latest.items()):
            report.entities_checked += 1
            if entity_id not in online_ids:
                report.missing_online.append(entity_id)
                continue
            row = self._online.get_row(view_name, entity_id)
            assert row is not None  # entity_ids and get_row agree by construction
            for feat in view.features:
                online_value = row.values.get(feat.name)
                offline_value = expected.get(feat.name)
                if online_value != offline_value:
                    report.mismatches.append(
                        FieldMismatch(
                            view_name=view_name,
                            entity_id=entity_id,
                            feature=feat.name,
                            online_value=online_value,
                            offline_value=offline_value,
                        )
                    )
        return report

    def check_all(self, view_names: list[str] | None, at: datetime) -> list[ParityReport]:
        names = view_names or [v.name for v in self._registry.list_views()]
        return [self.check_view(name, at) for name in names]
