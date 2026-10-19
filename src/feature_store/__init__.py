"""Feature Store.

A clean-room reference implementation of an enterprise feature store:
a validated feature registry, a versioned offline store with
point-in-time-correct joins, a low-latency online store, batch
materialization, offline/online parity checks, and a FastAPI serving
layer. All data is synthetic.
"""

from .consistency import ConsistencyChecker, ParityReport
from .definitions import Entity, Feature, FeatureType, FeatureView
from .materialization import MaterializationResult, Materializer
from .offline_store import FeatureRecord, OfflineStore
from .online_store import InMemoryOnlineStore, OnlineStore, SqliteOnlineStore
from .point_in_time import EntityRow, get_historical_features
from .registry import FeatureRegistry

__version__ = "0.1.0"

__all__ = [
    "ConsistencyChecker",
    "Entity",
    "EntityRow",
    "Feature",
    "FeatureRecord",
    "FeatureRegistry",
    "FeatureType",
    "FeatureView",
    "InMemoryOnlineStore",
    "MaterializationResult",
    "Materializer",
    "OfflineStore",
    "OnlineStore",
    "ParityReport",
    "SqliteOnlineStore",
    "get_historical_features",
]
