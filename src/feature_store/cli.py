"""Command-line entry points.

Usage:
    feature-store demo
    feature-store serve --port 8000
    feature-store views
    feature-store materialize --cutoff 2024-01-22T00:00:00+00:00
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone

from .materialization import Materializer
from .offline_store import OfflineStore
from .online_store import InMemoryOnlineStore
from .synthetic import build_demo_registry, generate_records


def _loaded() -> tuple:
    registry = build_demo_registry()
    offline = OfflineStore(registry)
    for view_name, records in generate_records().items():
        offline.write(view_name, records)
    online = InMemoryOnlineStore()
    return registry, offline, online


def _cmd_demo(args: argparse.Namespace) -> int:
    from .demo import run_demo

    run_demo()
    return 0


def _cmd_views(args: argparse.Namespace) -> int:
    registry, _, _ = _loaded()
    print(json.dumps([v.to_dict() for v in registry.list_views()], indent=2))
    return 0


def _cmd_materialize(args: argparse.Namespace) -> int:
    registry, offline, online = _loaded()
    cutoff = (
        datetime.fromisoformat(args.cutoff)
        if args.cutoff
        else datetime(2024, 1, 22, tzinfo=timezone.utc)
    )
    for result in Materializer(registry, offline, online).materialize(None, cutoff):
        print(
            f"{result.view_name}: wrote {result.rows_written} rows "
            f"({result.entities_considered} entities, cutoff {cutoff.isoformat()})"
        )
    return 0


def _cmd_serve(args: argparse.Namespace) -> int:
    import uvicorn

    from .serving import build_demo_app

    uvicorn.run(build_demo_app(), host=args.host, port=args.port)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="feature-store", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    demo = sub.add_parser("demo", help="Run the end-to-end demo")
    demo.set_defaults(func=_cmd_demo)

    views = sub.add_parser("views", help="List registered feature views as JSON")
    views.set_defaults(func=_cmd_views)

    mat = sub.add_parser("materialize", help="Materialize latest values to the online store")
    mat.add_argument("--cutoff", default=None, help="ISO-8601 cutoff timestamp")
    mat.set_defaults(func=_cmd_materialize)

    serve = sub.add_parser("serve", help="Run the FastAPI serving app (demo data)")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8000)
    serve.set_defaults(func=_cmd_serve)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
