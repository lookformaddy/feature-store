"""Feature definitions: entities, typed features, and feature views.

These are the *contracts* of the feature store. A feature view binds a set
of typed features to one entity, declares how long a value stays fresh
(its TTL), and is the unit of materialization, serving, and point-in-time
joins. Definitions are immutable once registered — changing a feature's
meaning means registering a new view, never mutating history.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any

from .errors import FeatureValidationError


class FeatureType(str, enum.Enum):
    INT = "int"
    FLOAT = "float"
    STRING = "string"
    BOOL = "bool"


def _type_matches(value: Any, ftype: FeatureType) -> bool:
    # bool is a subclass of int in Python — check it first, explicitly.
    if ftype is FeatureType.BOOL:
        return isinstance(value, bool)
    if ftype is FeatureType.INT:
        return isinstance(value, int) and not isinstance(value, bool)
    if ftype is FeatureType.FLOAT:
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if ftype is FeatureType.STRING:
        return isinstance(value, str)
    return False


def coerce_value(name: str, value: Any, ftype: FeatureType) -> Any:
    """Validate ``value`` against ``ftype`` and normalize it.

    Ints are accepted for float features and stored as floats so offline
    and online representations compare equal. Everything else must match
    exactly — silent coercion hides upstream data bugs.
    """
    if value is None:
        return None
    if not _type_matches(value, ftype):
        raise FeatureValidationError(
            f"feature {name!r} expects {ftype.value}, got {type(value).__name__}: {value!r}"
        )
    if ftype is FeatureType.FLOAT:
        return float(value)
    return value


@dataclass(frozen=True)
class Entity:
    """A join key domain, e.g. ``customer`` or ``product``."""

    name: str
    description: str = ""
    join_key: str = "entity_id"


@dataclass(frozen=True)
class Feature:
    """One typed feature inside a feature view."""

    name: str
    dtype: FeatureType
    description: str = ""


@dataclass(frozen=True)
class FeatureView:
    """A group of features about one entity, sharing source and TTL.

    ``ttl_seconds=None`` means values never expire (slowly-changing
    profile attributes). A finite TTL means a value older than the TTL,
    relative to the moment it is read or joined, is treated as missing —
    serving a stale feature is usually worse than serving none.
    """

    name: str
    entity: str
    features: tuple[Feature, ...]
    ttl_seconds: int | None = None
    description: str = ""
    tags: tuple[str, ...] = field(default_factory=tuple)

    @property
    def ttl(self) -> timedelta | None:
        return None if self.ttl_seconds is None else timedelta(seconds=self.ttl_seconds)

    def feature(self, name: str) -> Feature | None:
        for f in self.features:
            if f.name == name:
                return f
        return None

    def feature_names(self) -> list[str]:
        return [f.name for f in self.features]

    def validate_values(self, values: dict[str, Any]) -> dict[str, Any]:
        """Validate a record's values against this view's schema.

        Unknown features are rejected; missing features are allowed (a
        source batch may carry a subset) and read back as ``None``.
        Returns a normalized copy containing only declared features.
        """
        out: dict[str, Any] = {}
        for key, value in values.items():
            feat = self.feature(key)
            if feat is None:
                raise FeatureValidationError(
                    f"feature view {self.name!r} has no feature {key!r}"
                )
            out[key] = coerce_value(key, value, feat.dtype)
        return out

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "entity": self.entity,
            "features": [
                {"name": f.name, "dtype": f.dtype.value, "description": f.description}
                for f in self.features
            ],
            "ttl_seconds": self.ttl_seconds,
            "description": self.description,
            "tags": list(self.tags),
        }
