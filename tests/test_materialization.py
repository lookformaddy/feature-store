from feature_store.materialization import Materializer

from conftest import at


def test_materialize_writes_latest_at_cutoff(activity_history, registry, online):
    mat = Materializer(registry, activity_history, online)
    result = mat.materialize_view("customer_activity", at(7))
    assert result.entities_considered == 1
    assert result.rows_written == 1
    view = registry.get_view("customer_activity")
    got = online.get_features(view, "CUST-001", at=at(7, 13))
    assert got["orders_7d"] == 5  # Jan 5 value is latest at the Jan 7 cutoff


def test_materialize_never_writes_future_records(activity_history, registry, online):
    mat = Materializer(registry, activity_history, online)
    mat.materialize_view("customer_activity", at(2))
    view = registry.get_view("customer_activity")
    got = online.get_features(view, "CUST-001", at=at(2, 13))
    assert got["orders_7d"] == 1  # only the Jan 1 record exists by Jan 2


def test_materialize_all_populated(populated_offline, registry, online):
    mat = Materializer(registry, populated_offline, online)
    results = mat.materialize(None, at(22))
    by_view = {r.view_name: r for r in results}
    assert by_view["customer_activity"].rows_written == 10
    assert by_view["customer_profile"].rows_written == 10
    assert by_view["product_popularity"].rows_written == 6
    view = registry.get_view("customer_activity")
    latest_offline = populated_offline.records_for("customer_activity", "CUST-003")[-1]
    got = online.get_features(view, "CUST-003", at=at(22))
    assert got == latest_offline.values


def test_materialize_is_idempotent_in_values(activity_history, registry, online):
    mat = Materializer(registry, activity_history, online)
    mat.materialize_view("customer_activity", at(10, 12))
    first = online.get_row("customer_activity", "CUST-001")
    mat.materialize_view("customer_activity", at(10, 12))
    second = online.get_row("customer_activity", "CUST-001")
    assert first == second
    assert second.values["orders_7d"] == 9


def test_materialize_before_any_data_writes_nothing(offline, registry, online):
    mat = Materializer(registry, offline, online)
    result = mat.materialize_view("customer_activity", at(10))
    assert result.rows_written == 0
    assert online.entity_ids("customer_activity") == []
