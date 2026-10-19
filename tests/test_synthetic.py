from feature_store.synthetic import CUSTOMER_IDS, PRODUCT_IDS, generate_records


def test_deterministic_same_seed():
    a = generate_records(seed=7)
    b = generate_records(seed=7)
    for view in a:
        assert [(r.entity_id, r.event_timestamp, r.values) for r in a[view]] == [
            (r.entity_id, r.event_timestamp, r.values) for r in b[view]
        ]


def test_different_seed_differs():
    a = generate_records(seed=1)
    b = generate_records(seed=2)
    assert a["customer_activity"][0].values != b["customer_activity"][0].values or (
        a["customer_activity"][1].values != b["customer_activity"][1].values
    )


def test_coverage_and_counts():
    data = generate_records()
    assert len(data["customer_activity"]) == len(CUSTOMER_IDS) * 21
    assert len(data["product_popularity"]) == len(PRODUCT_IDS) * 21
    # profile is weekly: days 0, 7, 14 -> 3 records per customer
    assert len(data["customer_profile"]) == len(CUSTOMER_IDS) * 3


def test_timestamps_increase_per_entity():
    data = generate_records()
    rows = [r for r in data["customer_activity"] if r.entity_id == "CUST-001"]
    stamps = [r.event_timestamp for r in rows]
    assert stamps == sorted(stamps)
