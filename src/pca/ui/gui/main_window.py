"""MainWindow for the native PyQt6 GUI.

The window is split into three tabs (Inventory / Recommend / Quote), a
menu bar with File / Help actions, and a status bar that reflects the
currently loaded snapshot + market files.

All cross-cutting state is held by :class:`GuiController`; the widgets
here are dumb - they call the controller and render whatever comes back.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QAction, QKeySequence
from PyQt6.QtWidgets import (
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QStatusBar,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from pca.core.models import Workload
from pca.ui.gui.controller import GuiController

_WORKLOADS: list[tuple[str, Workload]] = [
    ("Gaming - 1080p", Workload.GAMING_1080P),
    ("Gaming - 1440p", Workload.GAMING_1440P),
    ("Gaming - 4K", Workload.GAMING_4K),
    ("Productivity", Workload.PRODUCTIVITY),
    ("Content creation", Workload.CONTENT_CREATION),
    ("ML workstation", Workload.ML_WORKSTATION),
]

_STRATEGIES: list[tuple[str, str]] = [
    ("Greedy (fast baseline)", "greedy"),
    ("ILP (optimal, linear)", "ilp"),
    ("Multi-objective (perf / power / noise)", "multi"),
]


# ---------------------------------------------------------------------------
# Helper widgets
# ---------------------------------------------------------------------------


def _make_table(headers: list[str]) -> QTableWidget:
    t = QTableWidget(0, len(headers))
    t.setHorizontalHeaderLabels(headers)
    t.verticalHeader().setVisible(False)
    t.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
    t.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
    t.setAlternatingRowColors(True)
    hdr = t.horizontalHeader()
    hdr.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
    return t


def _hline() -> QFrame:
    line = QFrame()
    line.setFrameShape(QFrame.Shape.HLine)
    line.setFrameShadow(QFrame.Shadow.Sunken)
    return line


# ---------------------------------------------------------------------------
# Tabs
# ---------------------------------------------------------------------------


class InventoryTab(QWidget):
    """Shows the loaded snapshot + deprecation warnings."""

    def __init__(self, controller: GuiController) -> None:
        super().__init__()
        self._controller = controller

        self._table = _make_table(["Kind", "Vendor", "Model", "Specs"])
        self._deprecations = QLabel("Load a snapshot to see deprecation warnings.")
        self._deprecations.setWordWrap(True)
        self._deprecations.setStyleSheet("color: #8a8f9a; padding: 4px 0;")

        load_btn = QPushButton("Load snapshot ...")
        load_btn.clicked.connect(self._load_snapshot_dialog)

        layout = QVBoxLayout(self)
        top = QHBoxLayout()
        top.addWidget(QLabel("<b>Hardware inventory</b>"))
        top.addStretch(1)
        top.addWidget(load_btn)
        layout.addLayout(top)
        layout.addWidget(_hline())
        layout.addWidget(self._deprecations)
        layout.addWidget(self._table, 1)

    def refresh(self) -> None:
        snap = self._controller.state.snapshot
        if snap is None:
            self._table.setRowCount(0)
            self._deprecations.setText("No snapshot loaded.")
            return
        comps = list(snap.components)
        self._table.setRowCount(len(comps))
        for row, c in enumerate(comps):
            self._table.setItem(row, 0, QTableWidgetItem(c.kind.value))
            self._table.setItem(row, 1, QTableWidgetItem(c.vendor))
            self._table.setItem(row, 2, QTableWidgetItem(c.model))
            specs = ", ".join(f"{k}={v}" for k, v in c.specs.items())
            self._table.setItem(row, 3, QTableWidgetItem(specs))
        deprecations = self._controller.state.deprecations
        if deprecations:
            bullets = "".join(f"<li>{w}</li>" for w in deprecations)
            self._deprecations.setText(
                f"<span style='color:#c94a4a;'><b>Deprecation warnings:</b></span>"
                f"<ul>{bullets}</ul>"
            )
        else:
            self._deprecations.setText(
                "<span style='color:#3a8a5a;'>No deprecated components detected.</span>"
            )

    def _load_snapshot_dialog(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Open snapshot JSON", "", "Snapshot (*.json);;All files (*)"
        )
        if not path:
            return
        try:
            self._controller.load_snapshot(Path(path))
        except Exception as exc:
            QMessageBox.critical(self, "Could not load snapshot", str(exc))
            return
        self.refresh()
        # Let the MainWindow update its status bar.
        win = self.window()
        if hasattr(win, "_refresh_status"):
            win._refresh_status()


class RecommendTab(QWidget):
    """Budget inputs + plan table."""

    def __init__(self, controller: GuiController) -> None:
        super().__init__()
        self._controller = controller

        self._budget = QDoubleSpinBox()
        self._budget.setRange(100.0, 100_000.0)
        self._budget.setSingleStep(50.0)
        self._budget.setDecimals(2)
        self._budget.setSuffix(" USD")
        self._budget.setValue(800.0)

        self._workload = QComboBox()
        for label, _wl in _WORKLOADS:
            self._workload.addItem(label)
        self._workload.setCurrentIndex(1)  # 1440p

        self._strategy = QComboBox()
        for label, _s in _STRATEGIES:
            self._strategy.addItem(label)
        self._strategy.setCurrentIndex(0)

        self._table = _make_table(
            ["Kind", "Vendor", "Model", "Price (USD)", "Uplift %", "Rationale"]
        )
        self._summary = QLabel("No plan yet.")
        self._summary.setStyleSheet(
            "font-weight: 600; padding: 6px 0; font-size: 14px;"
        )

        run_btn = QPushButton("Recommend")
        run_btn.setDefault(True)
        run_btn.clicked.connect(self.run)

        form = QFormLayout()
        form.addRow("Budget", self._budget)
        form.addRow("Workload", self._workload)
        form.addRow("Strategy", self._strategy)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("<b>Upgrade plan</b>"))
        layout.addLayout(form)
        btn_row = QHBoxLayout()
        btn_row.addWidget(run_btn)
        btn_row.addStretch(1)
        layout.addLayout(btn_row)
        layout.addWidget(_hline())
        layout.addWidget(self._summary)
        layout.addWidget(self._table, 1)

    def run(self) -> None:
        snap = self._controller.state.snapshot
        if snap is None:
            QMessageBox.warning(
                self, "No snapshot", "Load a snapshot on the Inventory tab first."
            )
            return
        if not self._controller.state.market_items:
            QMessageBox.warning(
                self,
                "No market snapshot",
                "Use File > Open market snapshot to load a market fixture.",
            )
            return
        try:
            budget = Decimal(str(self._budget.value()))
        except InvalidOperation:
            QMessageBox.warning(self, "Bad budget", "Budget must be numeric.")
            return
        workload = _WORKLOADS[self._workload.currentIndex()][1]
        strategy = _STRATEGIES[self._strategy.currentIndex()][1]
        try:
            plan = self._controller.recommend(
                budget_usd=budget, workload=workload, strategy=strategy
            )
        except Exception as exc:
            QMessageBox.critical(self, "Recommendation failed", str(exc))
            return
        self._render(plan)

    def _render(self, plan) -> None:  # type: ignore[no-untyped-def]
        self._table.setRowCount(len(plan.items))
        for row, it in enumerate(plan.items):
            self._table.setItem(row, 0, QTableWidgetItem(it.kind.value))
            self._table.setItem(row, 1, QTableWidgetItem(it.market_item.vendor))
            self._table.setItem(row, 2, QTableWidgetItem(it.market_item.model))
            self._table.setItem(
                row, 3, QTableWidgetItem(f"${it.market_item.price_usd:.2f}")
            )
            self._table.setItem(row, 4, QTableWidgetItem(f"+{it.perf_uplift_pct:.1f}"))
            self._table.setItem(row, 5, QTableWidgetItem(it.rationale))
        self._summary.setText(
            f"Strategy: {plan.strategy} &nbsp;|&nbsp; "
            f"Plan total: <b>${plan.total_usd:.2f}</b> &nbsp;|&nbsp; "
            f"Overall uplift: <b>+{plan.overall_perf_uplift_pct:.1f}%</b>"
        )


class QuoteTab(QWidget):
    """Quote inputs + totals + export."""

    def __init__(self, controller: GuiController) -> None:
        super().__init__()
        self._controller = controller

        self._budget = QDoubleSpinBox()
        self._budget.setRange(100.0, 100_000.0)
        self._budget.setSingleStep(50.0)
        self._budget.setDecimals(2)
        self._budget.setSuffix(" USD")
        self._budget.setValue(800.0)

        self._workload = QComboBox()
        for label, _wl in _WORKLOADS:
            self._workload.addItem(label)
        self._workload.setCurrentIndex(1)

        self._strategy = QComboBox()
        for label, _s in _STRATEGIES:
            self._strategy.addItem(label)

        self._zip = QLineEdit()
        self._zip.setPlaceholderText("optional, 5 digits")
        self._zip.setMaxLength(5)

        self._totals = QTextEdit()
        self._totals.setReadOnly(True)
        self._totals.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._totals.setFixedHeight(120)
        self._totals.setStyleSheet(
            "font-family: Consolas, 'Cascadia Code', monospace; font-size: 13px;"
        )
        self._totals.setPlainText("No quote yet.")

        self._table = _make_table(
            ["Kind", "Vendor", "Model", "Price (USD)"]
        )

        run_btn = QPushButton("Generate quote")
        run_btn.setDefault(True)
        run_btn.clicked.connect(self.run)

        export_btn = QPushButton("Export HTML + JSON ...")
        export_btn.clicked.connect(self.export)

        form = QFormLayout()
        form.addRow("Budget", self._budget)
        form.addRow("Workload", self._workload)
        form.addRow("Strategy", self._strategy)
        form.addRow("US ZIP (tax)", self._zip)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("<b>Quote</b>"))
        layout.addLayout(form)
        btn_row = QHBoxLayout()
        btn_row.addWidget(run_btn)
        btn_row.addWidget(export_btn)
        btn_row.addStretch(1)
        layout.addLayout(btn_row)
        layout.addWidget(_hline())
        layout.addWidget(self._totals)
        layout.addWidget(self._table, 1)

    def run(self) -> None:
        snap = self._controller.state.snapshot
        if snap is None:
            QMessageBox.warning(self, "No snapshot", "Load a snapshot first.")
            return
        if not self._controller.state.market_items:
            QMessageBox.warning(
                self,
                "No market",
                "Load a market snapshot (File > Open market snapshot).",
            )
            return
        try:
            budget = Decimal(str(self._budget.value()))
        except InvalidOperation:
            QMessageBox.warning(self, "Bad budget", "Budget must be numeric.")
            return
        workload = _WORKLOADS[self._workload.currentIndex()][1]
        strategy = _STRATEGIES[self._strategy.currentIndex()][1]
        zip_code = self._zip.text().strip() or None
        try:
            q = self._controller.quote(
                budget_usd=budget,
                workload=workload,
                strategy=strategy,
                zip_code=zip_code,
            )
        except Exception as exc:
            QMessageBox.critical(self, "Quote failed", str(exc))
            return
        self._render(q)

    def export(self) -> None:
        if self._controller.state.last_quote is None:
            QMessageBox.information(
                self, "No quote", "Generate a quote first, then export."
            )
            return
        target = QFileDialog.getExistingDirectory(self, "Choose output directory")
        if not target:
            return
        try:
            html = self._controller.export_quote(Path(target))
        except Exception as exc:
            QMessageBox.critical(self, "Export failed", str(exc))
            return
        QMessageBox.information(self, "Exported", f"Wrote:\n{html}")

    def _render(self, q) -> None:  # type: ignore[no-untyped-def]
        plan = q.plan
        self._table.setRowCount(len(plan.items))
        for row, it in enumerate(plan.items):
            self._table.setItem(row, 0, QTableWidgetItem(it.kind.value))
            self._table.setItem(row, 1, QTableWidgetItem(it.market_item.vendor))
            self._table.setItem(row, 2, QTableWidgetItem(it.market_item.model))
            self._table.setItem(
                row, 3, QTableWidgetItem(f"${it.market_item.price_usd:.2f}")
            )
        self._totals.setPlainText(
            f"Strategy     : {plan.strategy}\n"
            f"Subtotal     : ${plan.total_usd:>10.2f}\n"
            f"Tax          : ${q.tax_usd:>10.2f}\n"
            f"Shipping     : ${q.shipping_usd:>10.2f}\n"
            f"Grand total  : ${q.grand_total_usd:>10.2f}\n"
            f"Uplift (%)   : +{plan.overall_perf_uplift_pct:.1f}%"
        )


# ---------------------------------------------------------------------------
# MainWindow
# ---------------------------------------------------------------------------


class MainWindow(QMainWindow):
    """Top-level window - menu + tabs + status bar."""

    def __init__(self, controller: GuiController | None = None) -> None:
        super().__init__()
        self.setWindowTitle("PC Upgrade Advisor")
        self.resize(1100, 720)
        self._controller = controller or GuiController()

        self._inventory = InventoryTab(self._controller)
        self._recommend = RecommendTab(self._controller)
        self._quote = QuoteTab(self._controller)

        tabs = QTabWidget()
        tabs.addTab(self._inventory, "Inventory")
        tabs.addTab(self._recommend, "Recommend")
        tabs.addTab(self._quote, "Quote")
        self.setCentralWidget(tabs)

        self._status = QStatusBar()
        self.setStatusBar(self._status)

        self._build_menu()
        self._refresh_status()

    # -------- menu --------

    def _build_menu(self) -> None:
        bar = self.menuBar()
        file_menu = bar.addMenu("&File")

        open_snap = QAction("Open &snapshot ...", self)
        open_snap.setShortcut(QKeySequence.StandardKey.Open)
        open_snap.triggered.connect(self._open_snapshot)
        file_menu.addAction(open_snap)

        open_market = QAction("Open &market snapshot ...", self)
        open_market.setShortcut("Ctrl+M")
        open_market.triggered.connect(self._open_market)
        file_menu.addAction(open_market)

        file_menu.addSeparator()

        export_report = QAction("Export HTML &report ...", self)
        export_report.triggered.connect(self._export_report)
        file_menu.addAction(export_report)

        file_menu.addSeparator()

        quit_act = QAction("&Quit", self)
        quit_act.setShortcut(QKeySequence.StandardKey.Quit)
        quit_act.triggered.connect(self.close)
        file_menu.addAction(quit_act)

        help_menu = bar.addMenu("&Help")
        about = QAction("&About", self)
        about.triggered.connect(self._show_about)
        help_menu.addAction(about)

    # -------- actions --------

    def _open_snapshot(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Open snapshot JSON", "", "Snapshot (*.json);;All files (*)"
        )
        if not path:
            return
        try:
            self._controller.load_snapshot(Path(path))
        except Exception as exc:
            QMessageBox.critical(self, "Load failed", str(exc))
            return
        self._inventory.refresh()
        self._refresh_status()

    def _open_market(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Open market snapshot JSON",
            "",
            "Market snapshot (*.json);;All files (*)",
        )
        if not path:
            return
        try:
            self._controller.load_market(Path(path))
        except Exception as exc:
            QMessageBox.critical(self, "Load failed", str(exc))
            return
        self._refresh_status()

    def _export_report(self) -> None:
        if self._controller.state.snapshot is None:
            QMessageBox.information(self, "No snapshot", "Load a snapshot first.")
            return
        target = QFileDialog.getExistingDirectory(self, "Choose output directory")
        if not target:
            return
        try:
            path = self._controller.export_report(Path(target))
        except Exception as exc:
            QMessageBox.critical(self, "Export failed", str(exc))
            return
        QMessageBox.information(self, "Exported", f"Wrote:\n{path}")

    def _show_about(self) -> None:
        QMessageBox.about(
            self,
            "About",
            "<b>PC Upgrade Advisor</b><br>"
            "Inventory, benchmark, compare, and upgrade your PC within budget."
            "<br><br>Local-first. No telemetry.",
        )

    # -------- status --------

    def _refresh_status(self) -> None:
        snap = self._controller.state.snapshot
        items = self._controller.state.market_items
        parts: list[str] = []
        if snap is None:
            parts.append("snapshot: <none>")
        else:
            parts.append(f"snapshot: {snap.id} ({len(list(snap.components))} components)")
        parts.append(f"market: {len(items)} items")
        self._status.showMessage("   |   ".join(parts))
