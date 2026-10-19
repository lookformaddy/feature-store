"""Deterministic synthetic data and the demo registry.

Everything here is invented: generic customers (``CUST-001`` …) and
products (``SKU-001`` …) with plausible activity/profile/popularity
features over a fixed January-2024 timeline. Generation is seeded, so
the same seed produces byte-identical data in CI, in demos, and in
tests — a property real feature pipelines rely on for reproducibility.
"""

from __future__ import annotations

import random
from datetime import datetime, timedelta, timezone

from .definitions import Entity, Feature, FeatureType, FeatureView
from .offline_store import FeatureRecord
from .registry import FeatureRegistry

EPOCH = datetime(2024, 1, 1, tzinfo=timezone.utc)

CUSTOMER_IDS = [f"CUST-{i:03d}" for i in range(1, 11)]
PRODUCT_IDS = [f"SKU-{i:03d}" for i in range(1, 7)]
SEGMENTS = ["bargain", "regular", "enthusiast", "new"]


def build_demo_registry() -> FeatureRegistry:
    """The registry used by the demo, the CLI, and the serving app."""
    registry = FeatureRegistry()
    registry.register_entity(Entity("customer", "A retail customer"))
    registry.register_entity(Entity("product", "A catalog product"))
    registry.register_view(
        FeatureView(
            name="customer_activity",
            entity="customer",
            features=(
                Feature("orders_7d", FeatureType.INT, "Orders in the trailing 7 days"),
                Feature("spend_7d", FeatureType.FLOAT, "Spend in the trailing 7 days"),
                Feature("sessions_7d", FeatureType.INT, "Sessions in the trailing 7 days"),
            ),
            ttl_seconds=30 * 24 * 3600,
            description="Rolling 7-day customer activity aggregates.",
            tags=("customer", "activity"),
        )
    )
    registry.register_view(
        FeatureView(
            name="customer_profile",
            entity="customer",
            features=(
                Feature("segment", FeatureType.STRING, "Lifecycle segment"),
                Feature("tenure_days", FeatureType.INT, "Days since first order"),
                Feature("is_premium", FeatureType.BOOL, "Premium membership flag"),
            ),
            ttl_seconds=None,
            description="Slowly-changing customer profile attributes.",
            tags=("customer", "profile"),
        )
    )
    registry.register_view(
        FeatureView(
            name="product_popularity",
            entity="product",
            features=(
                Feature("views_24h", FeatureType.INT, "Product views in trailing 24h"),
                Feature("purchases_24h", FeatureType.INT, "Purchases in trailing 24h"),
                Feature("avg_rating", FeatureType.FLOAT, "Average rating"),
            ),
            ttl_seconds=7 * 24 * 3600,
            description="Rolling 24-hour product popularity signals.",
            tags=("product", "popularity"),
        )
    )
    return registry


def generate_records(
    seed: int = 42, days: int = 21
) -> dict[str, list[FeatureRecord]]:
    """Generate one record per entity per day, per view, deterministically."""
    rng = random.Random(seed)
    out: dict[str, list[FeatureRecord]] = {
        "customer_activity": [],
        "customer_profile": [],
        "product_popularity": [],
    }
    for cid in CUSTOMER_IDS:
        orders_base = rng.randint(0, 4)
        segment = rng.choice(SEGMENTS)
        premium = rng.random() < 0.3
        tenure0 = rng.randint(10, 900)
        for day in range(days):
            ts = EPOCH + timedelta(days=day, hours=6)
            orders = max(0, orders_base + rng.randint(-1, 2))
            out["customer_activity"].append(
                FeatureRecord(
                    entity_id=cid,
                    event_timestamp=ts,
                    created_timestamp=ts,
                    values={
                        "orders_7d": orders,
                        "spend_7d": round(orders * rng.uniform(18.0, 90.0), 2),
                        "sessions_7d": orders + rng.randint(0, 6),
                    },
                )
            )
            if day % 7 == 0:  # profile changes weekly — slowly-changing dimension
                out["customer_profile"].append(
                    FeatureRecord(
                        entity_id=cid,
                        event_timestamp=ts,
                        created_timestamp=ts,
                        values={
                            "segment": segment,
                            "tenure_days": tenure0 + day,
                            "is_premium": premium,
                        },
                    )
                )
    for pid in PRODUCT_IDS:
        views_base = rng.randint(50, 900)
        rating = round(rng.uniform(3.2, 4.9), 2)
        for day in range(days):
            ts = EPOCH + timedelta(days=day, hours=6)
            views = max(0, views_base + rng.randint(-60, 80))
            out["product_popularity"].append(
                FeatureRecord(
                    entity_id=pid,
                    event_timestamp=ts,
                    created_timestamp=ts,
                    values={
                        "views_24h": views,
                        "purchases_24h": max(0, int(views * rng.uniform(0.01, 0.09))),
                        "avg_rating": rating,
                    },
                )
            )
    return out
