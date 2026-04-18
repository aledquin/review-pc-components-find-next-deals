"""Unit tests for the chart module. No network, no filesystem I/O in the hot path."""

from __future__ import annotations

from pathlib import Path

import pytest

from pca.core.models import (
    BudgetConstraint,
    SystemSnapshot,
    Workload,
)
from pca.reporting import charts
from tests.fixtures import RIG_IDS, load_market_snapshot, load_rig


def test_png_bytes_start_with_magic() -> None:
    snap = load_rig("rig_mid")
    png = charts.snapshot_scores_png(snap)
    assert png.startswith(b"\x89PNG\r\n\x1a\n")


@pytest.mark.parametrize("rig_id", RIG_IDS)
def test_snapshot_chart_is_deterministic(rig_id: str) -> None:
    snap: SystemSnapshot = load_rig(rig_id)
    png_a = charts.snapshot_scores_png(snap)
    png_b = charts.snapshot_scores_png(snap)
    assert png_a == png_b


def test_png_as_data_url_has_prefix() -> None:
    url = charts.png_as_data_url(b"\x89PNG\r\n\x1a\ntiny")
    assert url.startswith("data:image/png;base64,")


def test_write_chart_creates_parents(tmp_path: Path) -> None:
    target = tmp_path / "deep" / "nested" / "chart.png"
    path = charts.write_chart(b"\x89PNG\r\n\x1a\ntiny", target)
    assert path.exists()
    assert path.read_bytes().startswith(b"\x89PNG")


def test_plan_uplift_chart_is_png_for_small_plan() -> None:
    from pca.budget.optimizer_greedy import optimize_greedy

    snap = load_rig("rig_budget")
    items, _ = load_market_snapshot("snapshot_normal")
    from decimal import Decimal

    constraint = BudgetConstraint(
        max_usd=Decimal("600"),
        target_workload=Workload.GAMING_1080P,
    )
    plan = optimize_greedy(snap, constraint, items)
    png = charts.plan_uplift_png(plan, snap, Workload.GAMING_1080P)
    assert png.startswith(b"\x89PNG\r\n\x1a\n")
