"""Serving API (FastAPI): online features + historical datasets.

Two read paths, one contract:

- ``POST /online-features`` — the low-latency path a model calls at
  prediction time; values come from the online store.
- ``POST /historical-dataset`` — the training path; values come from the
  offline store through the point-in-time join.

Both resolve feature views through the same registry, which is the
structural reason training and serving agree on what a feature *is*.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from .consistency import ConsistencyChecker
from .errors import FeatureStoreError
from .materialization import Materializer
from .offline_store import OfflineStore
from .online_store import OnlineStore
from .point_in_time import EntityRow, get_historical_features
from .registry import FeatureRegistry
from .synthetic import build_demo_registry, generate_records


class OnlineFeaturesRequest(BaseModel):
    feature_view: str
    entity_ids: list[str]
    feature_names: list[str] | None = None
    at: datetime | None = None


class EntityRowIn(BaseModel):
    entity_id: str
    event_timestamp: datetime
    label: Any = None


class HistoricalDatasetRequest(BaseModel):
    feature_views: list[str]
    entity_rows: list[EntityRowIn]


class MaterializeRequest(BaseModel):
    feature_views: list[str] | None = None
    cutoff: datetime | None = None


def create_app(
    registry: FeatureRegistry,
    offline: OfflineStore,
    online: OnlineStore,
) -> FastAPI:
    app = FastAPI(title="Feature Store", version="0.1.0")
    materializer = Materializer(registry, offline, online)
    checker = ConsistencyChecker(registry, offline, online)

    @app.get("/health")
    def health() -> dict[str, Any]:
        return {"status": "ok", "feature_views": [v.name for v in registry.list_views()]}

    @app.get("/feature-views")
    def list_views() -> dict[str, Any]:
        return {"feature_views": [v.to_dict() for v in registry.list_views()]}

    @app.get("/feature-views/{name}")
    def get_view(name: str) -> dict[str, Any]:
        try:
            return registry.get_view(name).to_dict()
        except FeatureStoreError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.post("/online-features")
    def online_features(req: OnlineFeaturesRequest) -> dict[str, Any]:
        try:
            view = registry.get_view(req.feature_view)
        except FeatureStoreError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        at = req.at or datetime.now(timezone.utc)
        features = {
            eid: online.get_features(view, eid, req.feature_names, at=at)
            for eid in req.entity_ids
        }
        return {"feature_view": view.name, "at": at, "features": features}

    @app.post("/historical-dataset")
    def historical_dataset(req: HistoricalDatasetRequest) -> dict[str, Any]:
        try:
            rows = get_historical_features(
                registry,
                offline,
                [
                    EntityRow(r.entity_id, r.event_timestamp, r.label)
                    for r in req.entity_rows
                ],
                req.feature_views,
            )
        except FeatureStoreError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return {"rows": rows, "count": len(rows)}

    @app.post("/materialize")
    def materialize(req: MaterializeRequest) -> dict[str, Any]:
        cutoff = req.cutoff or datetime.now(timezone.utc)
        try:
            results = materializer.materialize(req.feature_views, cutoff)
        except FeatureStoreError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return {
            "cutoff": cutoff,
            "results": [
                {
                    "view": r.view_name,
                    "entities_considered": r.entities_considered,
                    "rows_written": r.rows_written,
                    "rows_skipped_stale": r.rows_skipped_stale,
                }
                for r in results
            ],
        }

    @app.get("/consistency/{view_name}")
    def consistency(view_name: str, at: datetime | None = None) -> dict[str, Any]:
        try:
            report = checker.check_view(view_name, at or datetime.now(timezone.utc))
        except FeatureStoreError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return {
            "view": report.view_name,
            "ok": report.ok,
            "entities_checked": report.entities_checked,
            "mismatches": [vars(m) for m in report.mismatches],
            "missing_online": report.missing_online,
        }

    return app


def build_demo_app(online: OnlineStore | None = None) -> FastAPI:
    """An app pre-loaded with the synthetic dataset, materialized to its end."""
    from .online_store import InMemoryOnlineStore

    registry = build_demo_registry()
    offline = OfflineStore(registry)
    for view_name, records in generate_records().items():
        offline.write(view_name, records)
    online = online or InMemoryOnlineStore()
    Materializer(registry, offline, online).materialize(
        None, datetime(2024, 1, 22, tzinfo=timezone.utc)
    )
    return create_app(registry, offline, online)


# For `uvicorn feature_store.serving:app`.
app = build_demo_app()
