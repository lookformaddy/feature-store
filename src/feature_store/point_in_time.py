"""Point-in-time (as-of) joins: the heart of the feature store.

A training row is labelled at a moment in time — say, the moment a
customer placed an order. The features joined onto that row must be the
values that were true *at that moment*: the latest value with
``event_timestamp <= label_timestamp``, and never a value from after it.
Joining "the latest value, period" leaks the future into training and
produces models that look brilliant offline and fail in production,
because at serving time the future has not happened yet.

This module implements that as-of semantics exactly, with TTL expiry on
top: a value that was already stale at the label timestamp joins as
``None``, just as the online store would have refused to serve it.
"""

from __future__ import annotations

import bisect
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Iterable

from .offline_store import OfflineStore
from .registry import FeatureRegistry


@dataclass(frozen=True)
class EntityRow:
    """One row of the training spine: an entity and its label timestamp."""

    entity_id: str
    event_timestamp: datetime
    label: Any = None


def _as_of_value(
    timestamps: list[datetime],
    at: datetime,
    ttl_seconds: int | None,
) -> int | None:
    """Index of the latest record at-or-before ``at``, or None.

    ``timestamps`` must be sorted ascending (as-of order). An index is
    returned only if a record exists at-or-before ``at`` *and* it was
    still within its TTL at ``at``.
    """
    idx = bisect.bisect_right(timestamps, at) - 1
    if idx < 0:
        return None
    if ttl_seconds is not None:
        age = (at - timestamps[idx]).total_seconds()
        if age > ttl_seconds:
            return None
    return idx


def get_historical_features(
    registry: FeatureRegistry,
    offline: OfflineStore,
    entity_rows: Iterable[EntityRow | dict[str, Any]],
    feature_view_names: list[str],
) -> list[dict[str, Any]]:
    """Build a point-in-time-correct training dataset.

    For each entity row and each requested view, every feature takes the
    value from the latest record with ``event_timestamp <=`` the row's
    timestamp, subject to the view's TTL. Output rows carry
    ``entity_id``, ``event_timestamp``, ``label`` (when present), and one
    key per feature named ``<view>__<feature>`` so features from
    different views can never collide.
    """
    views = [registry.get_view(name) for name in feature_view_names]

    # Pre-sort each view's per-entity history once: O(R log R) total,
    # then each lookup is a binary search instead of a scan.
    histories: dict[str, dict[str, tuple[list[datetime], list[dict[str, Any]]]]] = {}
    for view in views:
        per_entity: dict[str, tuple[list[datetime], list[dict[str, Any]]]] = {}
        for entity_id in offline.entity_ids(view.name):
            records = offline.records_for(view.name, entity_id)
            per_entity[entity_id] = (
                [r.event_timestamp for r in records],
                [r.values for r in records],
            )
        histories[view.name] = per_entity

    out: list[dict[str, Any]] = []
    for raw in entity_rows:
        row = (
            raw
            if isinstance(raw, EntityRow)
            else EntityRow(
                entity_id=str(raw["entity_id"]),
                event_timestamp=raw["event_timestamp"],
                label=raw.get("label"),
            )
        )
        result: dict[str, Any] = {
            "entity_id": row.entity_id,
            "event_timestamp": row.event_timestamp,
        }
        if row.label is not None:
            result["label"] = row.label
        for view in views:
            timestamps, values_list = histories[view.name].get(row.entity_id, ([], []))
            idx = _as_of_value(timestamps, row.event_timestamp, view.ttl_seconds)
            values = values_list[idx] if idx is not None else {}
            for feat in view.features:
                result[f"{view.name}__{feat.name}"] = values.get(feat.name)
        out.append(result)
    return out
