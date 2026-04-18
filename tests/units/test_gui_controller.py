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


# ---------------------- detect + save snapshot ----------------------


def test_detect_snapshot_uses_injected_probe(monkeypatch: pytest.MonkeyPatch) -> None:
    """detect_snapshot() should call detect_probe() and cache the result."""
    from pca.core.models import SystemSnapshot

    from tests.fixtures import INV_DIR

    fake_snap = SystemSnapshot.model_validate_json(
        (INV_DIR / "rig_mid.json").read_text(encoding="utf-8")
    )

    class _FakeProbe:
        def collect(self) -> SystemSnapshot:
            return fake_snap

    monkeypatch.setattr(
        "pca.ui.gui.controller.detect_probe", lambda: _FakeProbe()
    )

    c = GuiController()
    snap = c.detect_snapshot()
    assert snap is fake_snap
    assert c.state.snapshot is fake_snap
    # Deprecation scan should have run.
    assert isinstance(c.state.deprecations, tuple)


def test_detect_snapshot_propagates_probe_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from pca.core.errors import InventoryError

    class _Broken:
        def collect(self) -> object:
            raise InventoryError("no WMI")

    monkeypatch.setattr(
        "pca.ui.gui.controller.detect_probe", lambda: _Broken()
    )
    c = GuiController()
    with pytest.raises(InventoryError, match="no WMI"):
        c.detect_snapshot()
    assert c.state.snapshot is None


def test_save_snapshot_writes_json(ctl: GuiController, tmp_path: Path) -> None:
    out = ctl.save_snapshot(tmp_path / "mine.json")
    assert out.exists()
    assert out.read_text(encoding="utf-8").startswith("{")


def test_save_snapshot_requires_loaded_snapshot(tmp_path: Path) -> None:
    c = GuiController()
    with pytest.raises(RuntimeError, match="snapshot"):
        c.save_snapshot(tmp_path / "x.json")


# ---------------------- default market + auto-persist ----------------------


def test_load_default_market_populates_items() -> None:
    """The shipped default market catalog should load with no args."""
    c = GuiController()
    items, deals = c.load_default_market()
    assert items, "default market catalog must ship at least one item"
    assert c.state.market_items == items
    # Deals can be empty; just check the attribute exists.
    assert isinstance(deals, tuple)


def test_user_data_dir_is_writable(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """user_data_dir() should return a directory we can write to."""
    from pca.ui.gui.controller import user_data_dir

    monkeypatch.setenv("PCA_USER_DATA_DIR", str(tmp_path / "pca"))
    d = user_data_dir()
    assert d == tmp_path / "pca"
    d.mkdir(parents=True, exist_ok=True)
    probe = d / "hello.txt"
    probe.write_text("ok", encoding="utf-8")
    assert probe.read_text(encoding="utf-8") == "ok"


def test_detect_autosaves_to_user_data_dir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """After Detect, the snapshot is written to last_snapshot.json automatically."""
    from pca.core.models import SystemSnapshot

    fake = SystemSnapshot.model_validate_json(
        (INV_DIR / "rig_mid.json").read_text(encoding="utf-8")
    )

    class _Stub:
        def collect(self) -> SystemSnapshot:
            return fake

    monkeypatch.setenv("PCA_USER_DATA_DIR", str(tmp_path / "pca"))
    monkeypatch.setattr("pca.ui.gui.controller.detect_probe", lambda: _Stub())

    c = GuiController()
    c.detect_snapshot()

    expected = tmp_path / "pca" / "last_snapshot.json"
    assert expected.exists(), "detect should autosave to user data dir"
    assert '"rig_mid"' in expected.read_text(encoding="utf-8")


def test_load_last_snapshot_returns_persisted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """load_last_snapshot() picks up whatever detect_snapshot() saved."""
    from pca.core.models import SystemSnapshot

    fake = SystemSnapshot.model_validate_json(
        (INV_DIR / "rig_mid.json").read_text(encoding="utf-8")
    )

    class _Stub:
        def collect(self) -> SystemSnapshot:
            return fake

    monkeypatch.setenv("PCA_USER_DATA_DIR", str(tmp_path / "pca"))
    monkeypatch.setattr("pca.ui.gui.controller.detect_probe", lambda: _Stub())

    first = GuiController()
    first.detect_snapshot()

    # Brand new controller - should restore from disk.
    second = GuiController()
    restored = second.load_last_snapshot()
    assert restored is not None
    assert restored.id == fake.id
    assert second.state.snapshot is restored


def test_load_last_snapshot_returns_none_when_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("PCA_USER_DATA_DIR", str(tmp_path / "pca"))
    c = GuiController()
    assert c.load_last_snapshot() is None
