from datetime import datetime, timedelta, timezone

import pytest

from feature_store.offline_store import FeatureRecord, OfflineStore
from feature_store.online_store import InMemoryOnlineStore
from feature_store.synthetic import build_demo_registry, generate_records

UTC = timezone.utc
BASE = datetime(2024, 1, 1, 6, 0, tzinfo=UTC)


def at(day: int, hour: int = 12) -> datetime:
    """2024-01-<day> at <hour>:00 UTC — the tests' clock."""
    return BASE + timedelta(days=day - 1, hours=hour - 6)


@pytest.fixture()
def registry():
    return build_demo_registry()


@pytest.fixture()
def offline(registry) -> OfflineStore:
    return OfflineStore(registry)


@pytest.fixture()
def online() -> InMemoryOnlineStore:
    return InMemoryOnlineStore()


@pytest.fixture()
def populated_offline(registry) -> OfflineStore:
    store = OfflineStore(registry)
    for view_name, records in generate_records().items():
        store.write(view_name, records)
    return store


@pytest.fixture()
def activity_history(offline) -> OfflineStore:
    """CUST-001 activity: orders 1, 5, 9 on Jan 1, 5, 10 — hand-checkable."""
    offline.write(
        "customer_activity",
        [
            FeatureRecord("CUST-001", at(1, 6), {"orders_7d": 1, "spend_7d": 20.0, "sessions_7d": 2}),
            FeatureRecord("CUST-001", at(5, 6), {"orders_7d": 5, "spend_7d": 110.0, "sessions_7d": 7}),
            FeatureRecord("CUST-001", at(10, 6), {"orders_7d": 9, "spend_7d": 240.0, "sessions_7d": 11}),
        ],
    )
    return offline
