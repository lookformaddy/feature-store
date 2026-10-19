#!/usr/bin/env python3
"""Run the end-to-end feature-store demo (offline, no server needed).

Shows the leakage case the point-in-time join prevents, builds a
training dataset, materializes latest values to the online store,
serves one entity, and verifies offline/online parity.

    PYTHONPATH=src python examples/run_demo.py
    # equivalently: feature-store demo
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from feature_store.demo import run_demo

if __name__ == "__main__":
    run_demo()
