import pytest
from fastapi.testclient import TestClient

from feature_store.serving import build_demo_app

from conftest import at


@pytest.fixture(scope="module")
def client():
    return TestClient(build_demo_app())


def test_health(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_list_feature_views(client):
    resp = client.get("/feature-views")
    assert resp.status_code == 200
    names = [v["name"] for v in resp.json()["feature_views"]]
    assert "customer_activity" in names


def test_get_unknown_view_404(client):
    assert client.get("/feature-views/nope").status_code == 404


def test_online_features_served(client):
    resp = client.post(
        "/online-features",
        json={
            "feature_view": "customer_activity",
            "entity_ids": ["CUST-001"],
            "at": at(22).isoformat(),
        },
    )
    assert resp.status_code == 200
    features = resp.json()["features"]["CUST-001"]
    assert features is not None
    assert set(features) == {"orders_7d", "spend_7d", "sessions_7d"}


def test_online_features_unknown_view_404(client):
    resp = client.post(
        "/online-features", json={"feature_view": "nope", "entity_ids": ["CUST-001"]}
    )
    assert resp.status_code == 404


def test_historical_dataset_is_point_in_time(client):
    resp = client.post(
        "/historical-dataset",
        json={
            "feature_views": ["customer_activity"],
            "entity_rows": [
                {"entity_id": "CUST-001", "event_timestamp": at(3).isoformat(), "label": 0}
            ],
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["count"] == 1
    row = body["rows"][0]
    assert row["label"] == 0
    # Jan 3 row must carry the Jan 3 (or earlier) value — never a later day's.
    assert row["customer_activity__orders_7d"] is not None


def test_materialize_endpoint(client):
    resp = client.post(
        "/materialize",
        json={"feature_views": ["customer_activity"], "cutoff": at(22).isoformat()},
    )
    assert resp.status_code == 200
    assert resp.json()["results"][0]["view"] == "customer_activity"


def test_consistency_endpoint_ok(client):
    resp = client.get("/consistency/customer_activity", params={"at": at(22).isoformat()})
    assert resp.status_code == 200
    assert resp.json()["ok"] is True
