import pytest

from feature_store.errors import FeatureValidationError
from feature_store.offline_store import FeatureRecord

from conftest import at


def test_write_and_read_sorted(offline):
    offline.write(
        "customer_activity",
        [
            FeatureRecord("CUST-002", at(3, 6), {"orders_7d": 2, "spend_7d": 5.0, "sessions_7d": 1}),
            FeatureRecord("CUST-001", at(2, 6), {"orders_7d": 1, "spend_7d": 5.0, "sessions_7d": 1}),
        ],
    )
    rows = offline.read("customer_activity")
    assert [(r.entity_id, r.event_timestamp) for r in rows] == [
        ("CUST-001", at(2, 6)),
        ("CUST-002", at(3, 6)),
    ]


def test_batch_versions_increase(offline):
    v1 = offline.write(
        "customer_activity",
        [FeatureRecord("CUST-001", at(1, 6), {"orders_7d": 1, "spend_7d": 1.0, "sessions_7d": 1})],
    )
    v2 = offline.write(
        "customer_activity",
        [FeatureRecord("CUST-001", at(2, 6), {"orders_7d": 2, "spend_7d": 1.0, "sessions_7d": 1})],
    )
    assert (v1, v2, offline.current_version) == (1, 2, 2)


def test_dict_records_accepted_flat_and_nested(offline):
    offline.write(
        "customer_activity",
        [
            {"entity_id": "CUST-001", "event_timestamp": at(1, 6),
             "orders_7d": 3, "spend_7d": 9.5, "sessions_7d": 4},
            {"entity_id": "CUST-001", "event_timestamp": at(2, 6),
             "values": {"orders_7d": 4, "spend_7d": 9.5, "sessions_7d": 4}},
        ],
    )
    assert offline.record_count("customer_activity") == 2
    assert offline.records_for("customer_activity", "CUST-001")[0].values["orders_7d"] == 3


def test_wrong_type_rejected_at_write(offline):
    with pytest.raises(FeatureValidationError):
        offline.write(
            "customer_activity",
            [FeatureRecord("CUST-001", at(1, 6), {"orders_7d": "many"})],
        )


def test_bool_is_not_an_int(offline):
    with pytest.raises(FeatureValidationError):
        offline.write(
            "customer_activity",
            [FeatureRecord("CUST-001", at(1, 6), {"orders_7d": True})],
        )


def test_unknown_feature_rejected_at_write(offline):
    with pytest.raises(FeatureValidationError):
        offline.write(
            "customer_activity",
            [FeatureRecord("CUST-001", at(1, 6), {"orders_90d": 1})],
        )


def test_int_accepted_for_float_and_normalized(offline):
    offline.write(
        "customer_activity",
        [FeatureRecord("CUST-001", at(1, 6), {"spend_7d": 42})],
    )
    rec = offline.records_for("customer_activity", "CUST-001")[0]
    assert rec.values["spend_7d"] == 42.0
    assert isinstance(rec.values["spend_7d"], float)


def test_entity_ids_and_counts(populated_offline):
    assert populated_offline.entity_ids("customer_activity") == [
        f"CUST-{i:03d}" for i in range(1, 11)
    ]
    assert populated_offline.record_count("customer_activity") == 10 * 21
    assert populated_offline.record_count("product_popularity") == 6 * 21
