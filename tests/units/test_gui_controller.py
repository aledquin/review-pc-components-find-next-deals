"""Unit tests for the Qt-free GUI controller."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest

from pca.core.models import Workload
from pca.ui.gui.controller import GuiController
from tests.fixtures import INV_DIR, MARKET_DIR


@pytest.fixture
def ctl() -> GuiController:
    c = GuiController()
    c.load_snapshot(INV_DIR / "rig_mid.json")
    c.load_market(MARKET_DIR / "snapshot_normal.json")
    return c


def test_load_snapshot_populates_state() -> None:
    c = GuiController()
    snap = c.load_snapshot(INV_DIR / "rig_mid.json")
    assert c.state.snapshot is snap
    assert snap.id == "rig_mid"


def test_load_market_populates_items_and_deals() -> None:
    c = GuiController()
    items, deals = c.load_market(MARKET_DIR / "snapshot_normal.json")
    assert items, "expected at least one market item"
    assert c.state.market_items == items
    assert c.state.deals == deals


def test_recommend_requires_snapshot() -> None:
    c = GuiController()
    with pytest.raises(RuntimeError, match="snapshot"):
        c.recommend(budget_usd=Decimal("800"))


def test_recommend_requires_market(tmp_path: Path) -> None:
    c = GuiController()
    c.load_snapshot(INV_DIR / "rig_mid.json")
    with pytest.raises(RuntimeError, match="market"):
        c.recommend(budget_usd=Decimal("800"))


def test_recommend_returns_plan(ctl: GuiController) -> None:
    plan = ctl.recommend(
        budget_usd=Decimal("1200"),
        workload=Workload.GAMING_1440P,
        strategy="greedy",
    )
    assert plan.items, "expected at least one upgrade item"
    assert plan.total_usd <= Decimal("1200")
    assert ctl.state.last_plan is plan


def test_quote_pipeline(ctl: GuiController) -> None:
    q = ctl.quote(
        budget_usd=Decimal("800"),
        workload=Workload.GAMING_1440P,
        strategy="greedy",
        zip_code="98101",
    )
    assert q.tax_usd > Decimal("0")  # Seattle WA has sales tax
    assert q.grand_total_usd >= q.plan.total_usd
    assert ctl.state.last_quote is q


def test_multi_strategy_runs(ctl: GuiController) -> None:
    plan = ctl.recommend(budget_usd=Decimal("800"), strategy="multi")
    # Multi may or may not find anything feasible under a low cap; just
    # assert it returned a plan object with the right strategy tag.
    assert plan.strategy.startswith("multi") or plan.strategy == "multi"


def test_export_report_writes_html(ctl: GuiController, tmp_path: Path) -> None:
    out = ctl.export_report(tmp_path)
    assert out.exists()
    assert out.suffix == ".html"


def test_export_quote_without_prior_quote_errors(ctl: GuiController, tmp_path: Path) -> None:
    with pytest.raises(RuntimeError, match="quote"):
        ctl.export_quote(tmp_path)


def test_export_quote_after_building(ctl: GuiController, tmp_path: Path) -> None:
    ctl.quote(budget_usd=Decimal("1000"), zip_code="98101")
    out = ctl.export_quote(tmp_path)
    assert out.exists()
    assert "quote" in out.name
