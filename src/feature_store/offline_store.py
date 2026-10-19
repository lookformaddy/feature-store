"""The offline store: versioned, append-only historical feature tables.

The offline store answers "what was true at time T?" — it keeps *every*
version of every feature value, each stamped with:

- ``event_timestamp`` — when the value became true in the world, and
- ``created_timestamp`` — when the store learned about it (late-arriving
  corrections carry an old event time but a new created time).

Writes arrive in batches; each batch gets a monotonically increasing
version id so any historical snapshot is reproducible. Nothing is ever
updated in place: a correction is a new record, not a mutation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Iterable

from .registry import FeatureRegistry


@dataclass(frozen=True)
class FeatureRecord:
    """One version of one entity's feature values in one view."""

    entity_id: str
    event_timestamp: datetime
    values: dict[str, Any]
    created_timestamp: datetime | None = None
    batch_version: int = 0

    def value(self, feature: str) -> Any:
        return self.values.get(feature)


@dataclass
class _ViewTable:
    records: list[FeatureRecord] = field(default_factory=list)

    def sorted_records(self, entity_id: str) -> list[FeatureRecord]:
        rows = [r for r in self.records if r.entity_id == entity_id]
        # As-of ordering: event time first; for corrections sharing an
        # event time, the later-created record wins.
        return sorted(
            rows,
            key=lambda r: (
                r.event_timestamp,
                r.created_timestamp or r.event_timestamp,
                r.batch_version,
            ),
        )

    def entity_ids(self) -> list[str]:
        return sorted({r.entity_id for r in self.records})


class OfflineStore:
    def __init__(self, registry: FeatureRegistry) -> None:
        self._registry = registry
        self._tables: dict[str, _ViewTable] = {}
        self._next_version = 1

    @property
    def registry(self) -> FeatureRegistry:
        return self._registry

    def write(
        self,
        view_name: str,
        records: Iterable[FeatureRecord | dict[str, Any]],
        *,
        created_timestamp: datetime | None = None,
    ) -> int:
        """Append a batch of records to a view's table. Returns the batch version.

        Dict records look like ``{"entity_id": ..., "event_timestamp": ...,
        "values": {...}}`` (a flat dict with feature names as keys is also
        accepted). Values are validated against the view's schema — bad
        data fails at write time, not at training time.
        """
        view = self._registry.get_view(view_name)
        table = self._tables.setdefault(view_name, _ViewTable())
        version = self._next_version
        prepared: list[FeatureRecord] = []
        for raw in records:
            rec = self._coerce(raw, created_timestamp, version)
            prepared.append(
                FeatureRecord(
                    entity_id=rec.entity_id,
                    event_timestamp=rec.event_timestamp,
                    values=view.validate_values(rec.values),
                    created_timestamp=rec.created_timestamp,
                    batch_version=version,
                )
            )
        table.records.extend(prepared)
        self._next_version += 1
        return version

    @staticmethod
    def _coerce(
        raw: FeatureRecord | dict[str, Any],
        created_timestamp: datetime | None,
        version: int,
    ) -> FeatureRecord:
        if isinstance(raw, FeatureRecord):
            return FeatureRecord(
                entity_id=raw.entity_id,
                event_timestamp=raw.event_timestamp,
                values=dict(raw.values),
                created_timestamp=raw.created_timestamp or created_timestamp,
                batch_version=version,
            )
        entity_id = str(raw["entity_id"])
        event_ts = raw["event_timestamp"]
        if "values" in raw:
            values = dict(raw["values"])
        else:
            values = {
                k: v
                for k, v in raw.items()
                if k not in ("entity_id", "event_timestamp", "created_timestamp")
            }
        return FeatureRecord(
            entity_id=entity_id,
            event_timestamp=event_ts,
            values=values,
            created_timestamp=raw.get("created_timestamp") or created_timestamp,
            batch_version=version,
        )

    def read(self, view_name: str) -> list[FeatureRecord]:
        """All records for a view, sorted by (entity, event time, created time)."""
        self._registry.get_view(view_name)
        table = self._tables.get(view_name)
        if table is None:
            return []
        rows = list(table.records)
        return sorted(
            rows,
            key=lambda r: (
                r.entity_id,
                r.event_timestamp,
                r.created_timestamp or r.event_timestamp,
                r.batch_version,
            ),
        )

    def records_for(self, view_name: str, entity_id: str) -> list[FeatureRecord]:
        """One entity's history in one view, in as-of order."""
        self._registry.get_view(view_name)
        table = self._tables.get(view_name)
        if table is None:
            return []
        return table.sorted_records(entity_id)

    def entity_ids(self, view_name: str) -> list[str]:
        self._registry.get_view(view_name)
        table = self._tables.get(view_name)
        return [] if table is None else table.entity_ids()

    def record_count(self, view_name: str) -> int:
        self._registry.get_view(view_name)
        table = self._tables.get(view_name)
        return 0 if table is None else len(table.records)

    @property
    def current_version(self) -> int:
        """The most recently assigned batch version (0 if nothing written)."""
        return self._next_version - 1
