"""Point-in-time correctness: the guarantee the whole store exists for.

Rule under test: a joined feature is the latest value with
event_timestamp <= label timestamp — never after it — and a value that
had already exceeded its TTL at the label timestamp joins as None.
"""

from datetime import timedelta

from feature_store.offline_store import FeatureRecord
from feature_store.point_in_time import EntityRow, get_historical_features

from conftest import at


def _join(registry, offline, rows, views=("customer_activity",)):
    return get_historical_features(registry, offline, rows, list(views))


def test_latest_value_at_or_before_label(activity_history, registry):
    rows = _join(registry, activity_history, [EntityRow("CUST-001", at(7))])
    assert rows[0]["customer_activity__orders_7d"] == 5  # Jan 5 value, not Jan 10


def test_future_value_is_never_joined(activity_history, registry):
    # Label on Jan 9: the Jan 10 record (orders=9) is in the future.
    rows = _join(registry, activity_history, [EntityRow("CUST-001", at(9, 23))])
    assert rows[0]["customer_activity__orders_7d"] == 5


def test_exact_timestamp_match_is_included(activity_history, registry):
    rows = _join(registry, activity_history, [EntityRow("CUST-001", at(10, 6))])
    assert rows[0]["customer_activity__orders_7d"] == 9


def test_before_first_record_joins_as_none(activity_history, registry):
    rows = _join(registry, activity_history, [EntityRow("CUST-001", at(1, 0))])
    assert rows[0]["customer_activity__orders_7d"] is None


def test_unknown_entity_joins_as_none(activity_history, registry):
    rows = _join(registry, activity_history, [EntityRow("CUST-999", at(7))])
    assert rows[0]["customer_activity__orders_7d"] is None
    assert rows[0]["customer_activity__spend_7d"] is None


def test_label_is_carried_through(activity_history, registry):
    rows = _join(registry, activity_history, [EntityRow("CUST-001", at(7), label=1)])
    assert rows[0]["label"] == 1


def test_ttl_expiry_joins_as_none(activity_history, registry):
    # customer_activity TTL is 30 days; the Jan 10 record is stale by Feb 15.
    rows = _join(registry, activity_history, [EntityRow("CUST-001", at(10) + timedelta(days=36))])
    assert rows[0]["customer_activity__orders_7d"] is None


def test_ttl_boundary_is_still_fresh(activity_history, registry):
    # Exactly 30 days after the Jan 10 06:00 record: age == TTL, still fresh.
    label_at = at(10, 6) + timedelta(days=30)
    rows = _join(registry, activity_history, [EntityRow("CUST-001", label_at)])
    assert rows[0]["customer_activity__orders_7d"] == 9


def test_no_ttl_view_never_expires(offline, registry):
    offline.write(
        "customer_profile",
        [FeatureRecord("CUST-001", at(1, 6), {"segment": "regular", "tenure_days": 40, "is_premium": False})],
    )
    rows = _join(
        registry,
        offline,
        [EntityRow("CUST-001", at(1) + timedelta(days=400))],
        views=("customer_profile",),
    )
    assert rows[0]["customer_profile__segment"] == "regular"


def test_late_arriving_correction_wins_at_same_event_time(offline, registry):
    offline.write(
        "customer_activity",
        [FeatureRecord("CUST-001", at(5, 6), {"orders_7d": 5, "spend_7d": 1.0, "sessions_7d": 1})],
    )
    offline.write(
        "customer_activity",
        [
            FeatureRecord(
                "CUST-001",
                at(5, 6),
                {"orders_7d": 6, "spend_7d": 2.0, "sessions_7d": 2},
                created_timestamp=at(8, 6),
            )
        ],
    )
    rows = _join(registry, offline, [EntityRow("CUST-001", at(7))])
    assert rows[0]["customer_activity__orders_7d"] == 6


def test_multiple_views_and_entities(populated_offline, registry):
    spine = [
        EntityRow("CUST-002", at(15)),
        EntityRow("SKU-001", at(15)),
    ]
    # customer views for the customer row; product view for the product row
    rows = _join(
        registry, populated_offline, spine[:1], views=("customer_activity", "customer_profile")
    )
    assert rows[0]["customer_activity__orders_7d"] is not None
    assert rows[0]["customer_profile__segment"] is not None
    rows = _join(registry, populated_offline, spine[1:], views=("product_popularity",))
    assert rows[0]["product_popularity__views_24h"] is not None


def test_dict_entity_rows_accepted(activity_history, registry):
    rows = _join(
        registry,
        activity_history,
        [{"entity_id": "CUST-001", "event_timestamp": at(7), "label": "x"}],
    )
    assert rows[0]["customer_activity__orders_7d"] == 5
    assert rows[0]["label"] == "x"
