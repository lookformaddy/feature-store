from feature_store.consistency import ConsistencyChecker
from feature_store.materialization import Materializer

from conftest import at


def _materialized(populated_offline, registry, online):
    Materializer(registry, populated_offline, online).materialize(None, at(22))
    return ConsistencyChecker(registry, populated_offline, online)


def test_parity_ok_after_materialization(populated_offline, registry, online):
    checker = _materialized(populated_offline, registry, online)
    for report in checker.check_all(None, at(22)):
        assert report.ok, report.summary()
        assert report.entities_checked > 0


def test_parity_detects_tampered_online_value(populated_offline, registry, online):
    checker = _materialized(populated_offline, registry, online)
    view = registry.get_view("customer_activity")
    row = online.get_row("customer_activity", "CUST-001")
    tampered = dict(row.values, orders_7d=row.values["orders_7d"] + 1000)
    online.upsert(view, "CUST-001", tampered, row.event_timestamp)
    report = checker.check_view("customer_activity", at(22))
    assert not report.ok
    assert len(report.mismatches) == 1
    mismatch = report.mismatches[0]
    assert mismatch.entity_id == "CUST-001"
    assert mismatch.feature == "orders_7d"
    assert mismatch.online_value == mismatch.offline_value + 1000


def test_parity_reports_missing_online(populated_offline, registry, online):
    checker = _materialized(populated_offline, registry, online)
    online.delete("customer_activity", "CUST-002")
    report = checker.check_view("customer_activity", at(22))
    assert not report.ok
    assert report.missing_online == ["CUST-002"]


def test_parity_checked_at_earlier_time_uses_earlier_latest(populated_offline, registry, online):
    # Materialize only up to Jan 10, then check parity as of Jan 10: OK.
    Materializer(registry, populated_offline, online).materialize(None, at(10, 12))
    checker = ConsistencyChecker(registry, populated_offline, online)
    report = checker.check_view("customer_activity", at(10, 12))
    assert report.ok
