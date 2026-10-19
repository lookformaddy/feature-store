"""The online store: low-latency key-value serving of latest values.

Serving needs one thing: the current value of a view's features for one
entity, in milliseconds. The online store keeps exactly one row per
(view, entity) — the latest by event timestamp — behind a small
interface with two backends:

- ``InMemoryOnlineStore`` — dict-backed, for tests and local dev.
- ``SqliteOnlineStore`` — durable, zero-infrastructure, same semantics.

Freshness rule, shared by both: a write only replaces the stored row if
its event timestamp is at least as new as the stored one, so a delayed
batch can never resurrect stale values. TTL is enforced at read time
against a caller-supplied "now" (defaulting to the wall clock), which
keeps tests deterministic.
"""

from __future__ import annotations

import json
import sqlite3
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .definitions import FeatureView


@dataclass(frozen=True)
class OnlineRow:
    entity_id: str
    values: dict[str, Any]
    event_timestamp: datetime


def _is_fresh(view: FeatureView, row: OnlineRow, at: datetime) -> bool:
    if view.ttl_seconds is None:
        return True
    age = (at - row.event_timestamp).total_seconds()
    return 0 <= age <= view.ttl_seconds or age < 0


class OnlineStore(ABC):
    @abstractmethod
    def upsert(
        self, view: FeatureView, entity_id: str, values: dict[str, Any], event_timestamp: datetime
    ) -> bool:
        """Store values if not older than the current row. Returns True if written."""

    @abstractmethod
    def get_row(self, view_name: str, entity_id: str) -> OnlineRow | None:
        """The raw stored row, ignoring TTL (parity checks need this)."""

    @abstractmethod
    def delete(self, view_name: str, entity_id: str) -> None: ...

    @abstractmethod
    def entity_ids(self, view_name: str) -> list[str]: ...

    def get_features(
        self,
        view: FeatureView,
        entity_id: str,
        feature_names: list[str] | None = None,
        *,
        at: datetime | None = None,
    ) -> dict[str, Any] | None:
        """Served features for one entity, or None if absent or TTL-expired."""
        row = self.get_row(view.name, entity_id)
        if row is None:
            return None
        now = at or datetime.now(timezone.utc)
        if not _is_fresh(view, row, now):
            return None
        names = feature_names or view.feature_names()
        return {name: row.values.get(name) for name in names}


class InMemoryOnlineStore(OnlineStore):
    def __init__(self) -> None:
        self._rows: dict[tuple[str, str], OnlineRow] = {}

    def upsert(self, view, entity_id, values, event_timestamp) -> bool:
        key = (view.name, entity_id)
        existing = self._rows.get(key)
        if existing is not None and event_timestamp < existing.event_timestamp:
            return False
        self._rows[key] = OnlineRow(entity_id, view.validate_values(values), event_timestamp)
        return True

    def get_row(self, view_name, entity_id):
        return self._rows.get((view_name, entity_id))

    def delete(self, view_name, entity_id) -> None:
        self._rows.pop((view_name, entity_id), None)

    def entity_ids(self, view_name) -> list[str]:
        return sorted(eid for (vn, eid) in self._rows if vn == view_name)


class SqliteOnlineStore(OnlineStore):
    def __init__(self, path: str | Path = ":memory:") -> None:
        self._conn = sqlite3.connect(str(path))
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS online_features (
                view_name TEXT NOT NULL,
                entity_id TEXT NOT NULL,
                values_json TEXT NOT NULL,
                event_ts TEXT NOT NULL,
                PRIMARY KEY (view_name, entity_id)
            )
            """
        )
        self._conn.commit()

    def upsert(self, view, entity_id, values, event_timestamp) -> bool:
        existing = self.get_row(view.name, entity_id)
        if existing is not None and event_timestamp < existing.event_timestamp:
            return False
        self._conn.execute(
            "INSERT OR REPLACE INTO online_features VALUES (?, ?, ?, ?)",
            (
                view.name,
                entity_id,
                json.dumps(view.validate_values(values)),
                event_timestamp.isoformat(),
            ),
        )
        self._conn.commit()
        return True

    def get_row(self, view_name, entity_id):
        cur = self._conn.execute(
            "SELECT values_json, event_ts FROM online_features WHERE view_name=? AND entity_id=?",
            (view_name, entity_id),
        )
        row = cur.fetchone()
        if row is None:
            return None
        return OnlineRow(
            entity_id=entity_id,
            values=json.loads(row[0]),
            event_timestamp=datetime.fromisoformat(row[1]),
        )

    def delete(self, view_name, entity_id) -> None:
        self._conn.execute(
            "DELETE FROM online_features WHERE view_name=? AND entity_id=?",
            (view_name, entity_id),
        )
        self._conn.commit()

    def entity_ids(self, view_name) -> list[str]:
        cur = self._conn.execute(
            "SELECT entity_id FROM online_features WHERE view_name=? ORDER BY entity_id",
            (view_name,),
        )
        return [r[0] for r in cur.fetchall()]

    def close(self) -> None:
        self._conn.close()
