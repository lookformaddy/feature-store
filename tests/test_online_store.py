from datetime import timedelta

import pytest

from feature_store.online_store import InMemoryOnlineStore, SqliteOnlineStore

from conftest import at

VALUES = {"orders_7d": 5, "spend_7d": 110.0, "sessions_7d": 7}


@pytest.fixture(params=["memory", "sqlite"])
def store(request):
    if request.param == "memory":
        return InMemoryOnlineStore()
    return SqliteOnlineStore(":memory:")


def test_upsert_and_get(store, registry):
    view = registry.get_view("customer_activity")
    assert store.upsert(view, "CUST-001", VALUES, at(5, 6)) is True
    got = store.get_features(view, "CUST-001", at=at(5, 12))
    assert got == VALUES


def test_missing_entity_returns_none(store, registry):
    view = registry.get_view("customer_activity")
    assert store.get_features(view, "CUST-999", at=at(5)) is None


def test_older_write_never_clobbers_newer(store, registry):
    view = registry.get_view("customer_activity")
    store.upsert(view, "CUST-001", VALUES, at(5, 6))
    older = {"orders_7d": 1, "spend_7d": 1.0, "sessions_7d": 1}
    assert store.upsert(view, "CUST-001", older, at(3, 6)) is False
    assert store.get_features(view, "CUST-001", at=at(6))["orders_7d"] == 5


def test_newer_write_replaces(store, registry):
    view = registry.get_view("customer_activity")
    store.upsert(view, "CUST-001", VALUES, at(5, 6))
    newer = {"orders_7d": 9, "spend_7d": 1.0, "sessions_7d": 1}
    assert store.upsert(view, "CUST-001", newer, at(6, 6)) is True
    assert store.get_features(view, "CUST-001", at=at(6, 12))["orders_7d"] == 9


def test_ttl_expiry_at_read(store, registry):
    view = registry.get_view("customer_activity")  # TTL 30 days
    store.upsert(view, "CUST-001", VALUES, at(5, 6))
    assert store.get_features(view, "CUST-001", at=at(5, 6) + timedelta(days=31)) is None
    # ...but the raw row is still there for parity checks to see.
    assert store.get_row("customer_activity", "CUST-001") is not None


def test_feature_subset_selection(store, registry):
    view = registry.get_view("customer_activity")
    store.upsert(view, "CUST-001", VALUES, at(5, 6))
    got = store.get_features(view, "CUST-001", ["orders_7d"], at=at(5, 12))
    assert got == {"orders_7d": 5}


def test_delete_and_entity_ids(store, registry):
    view = registry.get_view("customer_activity")
    store.upsert(view, "CUST-002", VALUES, at(5, 6))
    store.upsert(view, "CUST-001", VALUES, at(5, 6))
    assert store.entity_ids("customer_activity") == ["CUST-001", "CUST-002"]
    store.delete("customer_activity", "CUST-001")
    assert store.entity_ids("customer_activity") == ["CUST-002"]
