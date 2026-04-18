"""Shared KGR loaders. Imported by functional tests.

All JSON files under ``tests/data/`` are the single source of truth; tests
never inline golden data.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pca.core.models import Deal, MarketItem, SystemSnapshot

DATA_DIR = Path(__file__).resolve().parent / "data"
INV_DIR = DATA_DIR / "inventories"
MARKET_DIR = DATA_DIR / "market_snapshots"
PLANS_DIR = DATA_DIR / "expected_plans"
QUOTES_DIR = DATA_DIR / "expected_quotes"
REPORTS_DIR = DATA_DIR / "expected_reports"

RIG_IDS: tuple[str, ...] = ("rig_budget", "rig_mid", "rig_highend")
SNAPSHOT_IDS: tuple[str, ...] = ("snapshot_normal", "snapshot_deal_heavy")


def load_rig(rig_id: str) -> SystemSnapshot:
    """Return a parsed ``SystemSnapshot`` for ``rig_id``."""
    path = INV_DIR / f"{rig_id}.json"
    return SystemSnapshot.model_validate_json(path.read_text(encoding="utf-8"))


def load_market_snapshot(snapshot_id: str) -> tuple[tuple[MarketItem, ...], tuple[Deal, ...]]:
    """Return ``(items, deals)`` from a market-snapshot fixture."""
    path = MARKET_DIR / f"{snapshot_id}.json"
    raw: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    items = tuple(MarketItem.model_validate(it) for it in raw["items"])
    deals = tuple(Deal.model_validate(d) for d in raw.get("deals", []))
    return items, deals


def load_json(path: Path) -> dict[str, Any]:
    """Read a JSON file into a dict. Used for golden-file comparisons."""
    return json.loads(path.read_text(encoding="utf-8"))
