"""Smoke tests for the native PyQt6 GUI.

These tests construct the real widgets under the ``offscreen`` Qt
platform so they run in headless CI (Linux/macOS/Windows) without a
display server. They exercise the same controller the MainWindow does,
so functional regressions in the core pipeline surface here too.
"""

from __future__ import annotations

import os
import sys
from collections.abc import Iterator
from decimal import Decimal

import pytest

# Force offscreen before importing Qt so no native display is opened.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PyQt6")

from PyQt6.QtWidgets import QApplication, QMessageBox  # noqa: E402

from pca.ui.gui.controller import GuiController  # noqa: E402
from tests.fixtures import INV_DIR, MARKET_DIR  # noqa: E402


@pytest.fixture(scope="session")
def qapp() -> Iterator[QApplication]:
    app = QApplication.instance() or QApplication(sys.argv)
    yield app  # type: ignore[misc]


@pytest.fixture(autouse=True)
def _silence_message_boxes(monkeypatch: pytest.MonkeyPatch) -> None:
    """Replace modal QMessageBox entries with no-op stubs.

    QMessageBox.warning / .critical / .information are blocking even
    under the offscreen Qt platform - pytest would hang forever waiting
    for the user to click OK. We stub them with a return value matching
    the ``StandardButton.Ok`` constant.
    """
    ok = QMessageBox.StandardButton.Ok
    for name in ("warning", "critical", "information", "question", "about"):
        monkeypatch.setattr(QMessageBox, name, lambda *args, **kwargs: ok)


@pytest.fixture
def controller() -> GuiController:
    c = GuiController()
    c.load_snapshot(INV_DIR / "rig_mid.json")
    c.load_market(MARKET_DIR / "snapshot_normal.json")
    return c


def test_main_window_constructs(qapp: QApplication, controller: GuiController) -> None:
    from pca.ui.gui.main_window import MainWindow

    win = MainWindow(controller)
    try:
        assert win.windowTitle() == "PC Upgrade Advisor"
        # Menu bar has actions (File, Help).
        titles = [a.text().replace("&", "") for a in win.menuBar().actions()]
        assert "File" in titles
        assert "Help" in titles
        # Status bar reflects the loaded snapshot.
        assert "rig_mid" in win.statusBar().currentMessage()
    finally:
        win.close()


def test_inventory_tab_refresh_populates_table(
    qapp: QApplication, controller: GuiController
) -> None:
    from pca.ui.gui.main_window import InventoryTab

    tab = InventoryTab(controller)
    tab.refresh()
    assert tab._table.rowCount() > 0


def test_recommend_tab_runs_plan(qapp: QApplication, controller: GuiController) -> None:
    from pca.ui.gui.main_window import RecommendTab

    tab = RecommendTab(controller)
    tab._budget.setValue(1200.0)
    tab.run()  # should not raise
    assert tab._table.rowCount() > 0
    assert "Plan total" in tab._summary.text()


def test_quote_tab_runs_and_sets_totals(
    qapp: QApplication, controller: GuiController
) -> None:
    from pca.ui.gui.main_window import QuoteTab

    tab = QuoteTab(controller)
    tab._budget.setValue(1200.0)
    tab._zip.setText("98101")
    tab.run()
    assert "Grand total" in tab._totals.toPlainText()
    assert controller.state.last_quote is not None
    assert controller.state.last_quote.tax_usd > Decimal("0")


def test_recommend_without_snapshot_shows_warning(qapp: QApplication) -> None:
    """Call run() with no loaded state - must not raise, warns via QMessageBox."""
    from pca.ui.gui.main_window import RecommendTab

    empty = GuiController()
    tab = RecommendTab(empty)
    # QMessageBox.warning is modal; we rely on offscreen platform to no-op it.
    # The important thing is that the call does not raise.
    tab.run()
    assert tab._table.rowCount() == 0
