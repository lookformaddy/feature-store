"""End-to-end demo: the leakage case the point-in-time join prevents.

Scenario: customer CUST-001's activity is recorded daily. A training row
is labelled on Jan 10 — did the customer churn? A naive "latest value"
join would attach the Jan 20 activity (orders collapsed to zero *after*
the label moment, partly *because* of the churn). The model would learn
"zero orders -> churn" from information that did not exist at prediction
time. The point-in-time join attaches the Jan 10 values instead.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from .consistency import ConsistencyChecker
from .materialization import Materializer
from .offline_store import OfflineStore
from .online_store import InMemoryOnlineStore
from .point_in_time import EntityRow, get_historical_features
from .synthetic import build_demo_registry, generate_records

UTC = timezone.utc


def run_demo() -> None:
    registry = build_demo_registry()
    offline = OfflineStore(registry)
    for view_name, records in generate_records().items():
        version = offline.write(view_name, records)
        print(f"offline: wrote {len(records):3d} records to {view_name} (batch v{version})")

    # -- The leakage case -------------------------------------------------
    # Find a customer whose activity actually changed after Jan 10, so the
    # naive join and the point-in-time join visibly disagree.
    label_time = datetime(2024, 1, 10, 12, 0, tzinfo=UTC)
    demo_entity, naive_latest, pit = None, None, None
    for cid in [f"CUST-{i:03d}" for i in range(1, 11)]:
        candidate_latest = offline.records_for("customer_activity", cid)[-1]
        candidate_pit = get_historical_features(
            registry, offline, [EntityRow(cid, label_time)], ["customer_activity"]
        )[0]
        if candidate_latest.values["orders_7d"] != candidate_pit["customer_activity__orders_7d"]:
            demo_entity, naive_latest, pit = cid, candidate_latest, candidate_pit
            break
    assert demo_entity is not None and naive_latest is not None and pit is not None
    print()
    print(f"Label moment: {label_time.isoformat()} ({demo_entity} churned)")
    print(
        "  NAIVE latest-join  -> "
        f"orders_7d={naive_latest.values['orders_7d']} "
        f"(value from {naive_latest.event_timestamp.date()}, AFTER the label: LEAKAGE)"
    )
    print(
        "  POINT-IN-TIME join -> "
        f"orders_7d={pit['customer_activity__orders_7d']} "
        "(latest value at-or-before the label moment: correct)"
    )
    assert naive_latest.event_timestamp > label_time
    assert naive_latest.values["orders_7d"] != pit["customer_activity__orders_7d"]

    # -- Training dataset ---------------------------------------------------
    spine = [
        EntityRow(cid, datetime(2024, 1, 15, 12, 0, tzinfo=UTC), label=i % 2)
        for i, cid in enumerate(["CUST-001", "CUST-002", "CUST-003"])
    ]
    dataset = get_historical_features(
        registry, offline, spine, ["customer_activity", "customer_profile"]
    )
    print()
    print(f"Training dataset: {len(dataset)} point-in-time-correct rows, e.g.")
    print(f"  {dataset[0]}")

    # -- Materialization + serving -------------------------------------------
    online = InMemoryOnlineStore()
    cutoff = datetime(2024, 1, 22, tzinfo=UTC)
    for result in Materializer(registry, offline, online).materialize(None, cutoff):
        print(
            f"materialized {result.view_name}: {result.rows_written} rows "
            f"({result.entities_considered} entities considered)"
        )
    view = registry.get_view("customer_activity")
    served = online.get_features(view, "CUST-001", at=cutoff + timedelta(hours=1))
    print(f"Online features for CUST-001 at serving time: {served}")

    # -- Parity ----------------------------------------------------------------
    for report in ConsistencyChecker(registry, offline, online).check_all(None, cutoff):
        print(f"parity: {report.summary()}")
        assert report.ok
    print()
    print("Demo complete: no future data in training rows, online == offline latest.")


if __name__ == "__main__":
    run_demo()
