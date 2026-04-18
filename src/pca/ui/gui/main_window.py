"""MainWindow for the native PyQt6 GUI.

The window is split into three tabs (Inventory / Recommend / Quote), a
menu bar with File / Help actions, and a status bar that reflects the
currently loaded snapshot + market files.

All cross-cutting state is held by :class:`GuiController`; the widgets
here are dumb - they call the controller and render whatever comes back.
"""

from __future__ import annotations

import html as _html
from decimal import Decimal, InvalidOperation
from pathlib import Path

from PyQt6.QtCore import QObject, Qt, QThread, pyqtSignal
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
    QProgressBar,
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
from pca.ui.common import (
    render_spec_diff_html,
    render_specs_list_html,
    safe_external_url,
)
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


def _make_table(
    headers: list[str],
    *,
    initial_widths: list[int] | None = None,
) -> QTableWidget:
    """Build a read-only table the user can freely resize and reorder.

    All columns are **Interactive** (drag a divider to resize), the last
    column stretches to absorb empty space, columns can be reordered by
    dragging the header, and row heights fit their contents so rich-HTML
    cells render fully without clipping.
    """

    t = QTableWidget(0, len(headers))
    t.setHorizontalHeaderLabels(headers)
    t.verticalHeader().setVisible(False)
    t.verticalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
    t.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
    t.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
    t.setAlternatingRowColors(True)
    t.setWordWrap(True)
    t.setShowGrid(True)
    hdr = t.horizontalHeader()
    hdr.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
    hdr.setStretchLastSection(True)
    hdr.setSectionsMovable(True)
    hdr.setHighlightSections(False)
    hdr.setDefaultAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
    if initial_widths:
        for i, width in enumerate(initial_widths):
            if width > 0 and i < len(headers):
                t.setColumnWidth(i, width)
    return t


def _hline() -> QFrame:
    line = QFrame()
    line.setFrameShape(QFrame.Shape.HLine)
    line.setFrameShadow(QFrame.Shadow.Sunken)
    return line


def _make_html_label(text: str) -> QLabel:
    """Build a rich-text QLabel for use as a table cell widget.

    - ``open_external_links`` so <a> tags launch the default browser.
    - ``word_wrap`` so rationale / long specs reflow in narrow columns.
    - Selectable text so users can copy model names or spec values.
    """

    label = QLabel(text)
    label.setTextFormat(Qt.TextFormat.RichText)
    label.setWordWrap(True)
    label.setOpenExternalLinks(True)
    label.setTextInteractionFlags(
        Qt.TextInteractionFlag.TextSelectableByMouse
        | Qt.TextInteractionFlag.LinksAccessibleByMouse
        | Qt.TextInteractionFlag.LinksAccessibleByKeyboard
    )
    label.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
    label.setContentsMargins(6, 4, 6, 4)
    label.setStyleSheet("background: transparent;")
    return label


def _format_upgrade_html(
    vendor: str,
    model: str,
    url: str | None,
    source: str | None,
    replaces_vendor: str | None = None,
    replaces_model: str | None = None,
) -> str:
    """Render the "Upgrade" cell: vendor, linked model, source badge,
    and a small 'replaces <old part>' line underneath."""

    safe = safe_external_url(url)
    esc_model = _html.escape(model)
    if safe is not None:
        model_html = (
            f'<a href="{_html.escape(safe, quote=True)}" '
            f'style="color:#4a90e2; text-decoration:none;" '
            f'title="Open product page">'
            f'{esc_model}'
            f' <span style="font-size:9px; color:#8a8f9a;">&#8599;</span>'
            f'</a>'
        )
    else:
        model_html = esc_model
    source_badge = ""
    if source:
        source_badge = (
            f' <span style="color:#3a8a5a; font-size:10px; padding:0 5px; '
            f'border:1px solid #3a8a5a; border-radius:6px;">'
            f'{_html.escape(source)}</span>'
        )
    replaces = ""
    rv = (replaces_vendor or "").strip()
    rm = (replaces_model or "").strip()
    if rv or rm:
        replaces = (
            f'<div style="color:#8a8f9a; font-size:10px; margin-top:2px;">'
            f'replaces <b>{_html.escape(rv)} {_html.escape(rm)}</b></div>'
        )
    return (
        f'<div><b>{_html.escape(vendor)}</b> {model_html}{source_badge}</div>'
        f'{replaces}'
    )


def _format_uplift_html(uplift_pct: float) -> str:
    color = "#3a8a5a" if uplift_pct > 0 else "#8a8f9a"
    weight = "600" if uplift_pct > 0 else "400"
    return (
        f'<span style="color:{color}; font-weight:{weight}; '
        f'font-family:Consolas, monospace;">+{uplift_pct:.1f}%</span>'
    )


# ---------------------------------------------------------------------------
# Background worker for hardware detection
# ---------------------------------------------------------------------------


class _DetectWorker(QObject):
    """Runs :meth:`GuiController.detect_snapshot` on a worker thread.

    WMI/lshw/system_profiler calls can take 2-5 seconds; doing them on
    the GUI thread would freeze the window. The worker runs in a moved
    :class:`QThread` and emits ``done`` / ``failed`` so the UI can
    re-render on the main thread.
    """

    done = pyqtSignal(object)  # SystemSnapshot
    failed = pyqtSignal(str)

    def __init__(self, controller: GuiController) -> None:
        super().__init__()
        self._controller = controller

    def run(self) -> None:
        try:
            snap = self._controller.detect_snapshot()
        except Exception as exc:
            self.failed.emit(str(exc))
            return
        self.done.emit(snap)


class _RefreshWorker(QObject):
    """Runs :meth:`GuiController.refresh_market_prices` on a worker thread.

    Retailer HTTP calls can take tens of seconds when multiple adapters
    are enabled. Keeping them off the GUI thread prevents the window
    from hanging.
    """

    done = pyqtSignal(object)  # RefreshResult
    failed = pyqtSignal(str)

    def __init__(self, controller: GuiController) -> None:
        super().__init__()
        self._controller = controller

    def run(self) -> None:
        try:
            result = self._controller.refresh_market_prices()
        except Exception as exc:
            self.failed.emit(str(exc))
            return
        self.done.emit(result)


# ---------------------------------------------------------------------------
# Tabs
# ---------------------------------------------------------------------------


class InventoryTab(QWidget):
    """Shows the loaded snapshot + deprecation warnings."""

    def __init__(self, controller: GuiController) -> None:
        super().__init__()
        self._controller = controller
        self._detect_thread: QThread | None = None
        self._detect_worker: _DetectWorker | None = None

        self._table = _make_table(
            ["Kind", "Vendor", "Model", "Specs"],
            initial_widths=[80, 140, 280, 420],
        )
        self._deprecations = QLabel("Load or detect a snapshot to see deprecation warnings.")
        self._deprecations.setWordWrap(True)
        self._deprecations.setStyleSheet("color: #8a8f9a; padding: 4px 0;")

        self._detect_btn = QPushButton("Detect this PC")
        self._detect_btn.setToolTip(
            "Inspect the local hardware with the native OS probe "
            "(WMI on Windows, lshw on Linux, system_profiler on macOS)."
        )
        self._detect_btn.clicked.connect(self._detect_clicked)

        self._save_btn = QPushButton("Save as JSON ...")
        self._save_btn.setToolTip("Persist the current snapshot to disk for later reuse.")
        self._save_btn.clicked.connect(self._save_clicked)
        self._save_btn.setEnabled(False)

        load_btn = QPushButton("Load snapshot ...")
        load_btn.clicked.connect(self._load_snapshot_dialog)

        self._busy = QProgressBar()
        self._busy.setRange(0, 0)  # indeterminate
        self._busy.setVisible(False)
        self._busy.setTextVisible(False)
        self._busy.setFixedHeight(4)

        layout = QVBoxLayout(self)
        top = QHBoxLayout()
        top.addWidget(QLabel("<b>Hardware inventory</b>"))
        top.addStretch(1)
        top.addWidget(self._detect_btn)
        top.addWidget(self._save_btn)
        top.addWidget(load_btn)
        layout.addLayout(top)
        layout.addWidget(self._busy)
        layout.addWidget(_hline())
        layout.addWidget(self._deprecations)
        layout.addWidget(self._table, 1)

    def refresh(self) -> None:
        snap = self._controller.state.snapshot
        self._save_btn.setEnabled(snap is not None)
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
            self._table.setCellWidget(
                row, 3, _make_html_label(render_specs_list_html(c.specs))
            )
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
        win = self.window()
        if hasattr(win, "_refresh_status"):
            win._refresh_status()

    # ---------------- detect this PC ----------------

    def _detect_clicked(self) -> None:
        if self._detect_thread is not None:
            return  # already running
        self._detect_btn.setEnabled(False)
        self._detect_btn.setText("Detecting ...")
        self._busy.setVisible(True)
        self._deprecations.setText(
            "Running the native hardware probe. This can take a few seconds on Windows."
        )

        thread = QThread(self)
        worker = _DetectWorker(self._controller)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.done.connect(self._on_detect_done)
        worker.failed.connect(self._on_detect_failed)
        worker.done.connect(thread.quit)
        worker.failed.connect(thread.quit)
        thread.finished.connect(thread.deleteLater)
        worker.done.connect(worker.deleteLater)
        worker.failed.connect(worker.deleteLater)
        self._detect_thread = thread
        self._detect_worker = worker
        thread.start()

    def _reset_detect_button(self) -> None:
        self._detect_btn.setEnabled(True)
        self._detect_btn.setText("Detect this PC")
        self._busy.setVisible(False)
        self._detect_thread = None
        self._detect_worker = None

    def _on_detect_done(self, _snap: object) -> None:
        self._reset_detect_button()
        self.refresh()
        win = self.window()
        if hasattr(win, "_refresh_status"):
            win._refresh_status()

    def _on_detect_failed(self, message: str) -> None:
        self._reset_detect_button()
        QMessageBox.critical(
            self,
            "Detection failed",
            f"The native hardware probe could not complete.\n\nDetails: {message}",
        )
        self._deprecations.setText(
            "<span style='color:#c94a4a;'>Detection failed. "
            "Try loading a snapshot file instead.</span>"
        )

    # ---------------- save ----------------

    def _save_clicked(self) -> None:
        if self._controller.state.snapshot is None:
            QMessageBox.information(self, "Nothing to save", "Detect or load a snapshot first.")
            return
        default = f"{self._controller.state.snapshot.id}.json"
        path, _ = QFileDialog.getSaveFileName(
            self, "Save snapshot", default, "Snapshot (*.json);;All files (*)"
        )
        if not path:
            return
        try:
            out = self._controller.save_snapshot(Path(path))
        except Exception as exc:
            QMessageBox.critical(self, "Save failed", str(exc))
            return
        QMessageBox.information(self, "Saved", f"Wrote:\n{out}")


class RecommendTab(QWidget):
    """Budget inputs + plan table."""

    def __init__(self, controller: GuiController) -> None:
        super().__init__()
        self._controller = controller
        self._refresh_thread: QThread | None = None
        self._refresh_worker: _RefreshWorker | None = None

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
            [
                "Kind",
                "Upgrade",
                "Price (USD)",
                "Uplift %",
                "Improved specs",
                "Rationale",
            ],
            initial_widths=[70, 300, 100, 90, 320, 300],
        )
        self._summary = QLabel("No plan yet.")
        self._summary.setStyleSheet(
            "font-weight: 600; padding: 6px 0; font-size: 14px;"
        )

        self._market_label = QLabel()
        self._market_label.setWordWrap(True)
        self._refresh_btn = QPushButton("Refresh prices")
        self._refresh_btn.clicked.connect(self._on_refresh_clicked)
        self._refresh_progress = QProgressBar()
        self._refresh_progress.setRange(0, 0)
        self._refresh_progress.setVisible(False)
        self._refresh_progress.setMaximumHeight(8)
        self._update_market_label()

        run_btn = QPushButton("Recommend")
        run_btn.setDefault(True)
        run_btn.clicked.connect(self.run)

        form = QFormLayout()
        form.addRow("Budget", self._budget)
        form.addRow("Workload", self._workload)
        form.addRow("Strategy", self._strategy)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("<b>Upgrade plan</b>"))
        layout.addWidget(self._market_label)
        market_row = QHBoxLayout()
        market_row.addWidget(self._refresh_btn)
        market_row.addWidget(self._refresh_progress, 1)
        layout.addLayout(market_row)
        layout.addLayout(form)
        btn_row = QHBoxLayout()
        btn_row.addWidget(run_btn)
        btn_row.addStretch(1)
        layout.addLayout(btn_row)
        layout.addWidget(_hline())
        layout.addWidget(self._summary)
        layout.addWidget(self._table, 1)

    def _update_market_label(self) -> None:
        st = self._controller.state
        if not st.market_items:
            self._market_label.setText(
                "<span style='color:#c87a00;'>No market data loaded yet. "
                "Click <b>Refresh prices</b> (needs API keys) or use "
                "<i>File &gt; Open market snapshot</i>.</span>"
            )
            return
        parts: list[str] = [f"<b>{len(st.market_items)}</b> items"]
        if st.market_sources:
            parts.append("sources: " + ", ".join(st.market_sources))
        if st.market_generated_at is not None:
            from pca.market.refresh import market_snapshot_age_days

            age = market_snapshot_age_days(st.market_generated_at)
            if age <= 0:
                parts.append("just refreshed")
            elif age > 14:
                parts.append(
                    f"<span style='color:#c87a00;'><b>stale</b> ({age} days old - "
                    f"consider refreshing)</span>"
                )
            else:
                parts.append(f"{age} day(s) old")
        self._market_label.setText(" &nbsp;|&nbsp; ".join(parts))

    def _on_refresh_clicked(self) -> None:
        if self._refresh_thread is not None:
            return  # already running
        if self._controller.state.snapshot is None:
            QMessageBox.warning(
                self,
                "No snapshot",
                "Load or detect a snapshot on the Inventory tab before "
                "refreshing prices.",
            )
            return

        self._refresh_btn.setEnabled(False)
        self._refresh_progress.setVisible(True)

        thread = QThread(self)
        worker = _RefreshWorker(self._controller)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.done.connect(self._on_refresh_done)
        worker.failed.connect(self._on_refresh_failed)
        worker.done.connect(thread.quit)
        worker.failed.connect(thread.quit)
        thread.finished.connect(worker.deleteLater)
        thread.finished.connect(self._teardown_refresh_thread)
        self._refresh_thread = thread
        self._refresh_worker = worker
        thread.start()

    def _teardown_refresh_thread(self) -> None:
        if self._refresh_thread is not None:
            self._refresh_thread.deleteLater()
        self._refresh_thread = None
        self._refresh_worker = None
        self._refresh_btn.setEnabled(True)
        self._refresh_progress.setVisible(False)

    def _on_refresh_done(self, result: object) -> None:
        # result is a RefreshResult; keep the type loose so we don't
        # bring the import in at module-load time.
        errors = tuple(getattr(result, "errors", ()))
        items = tuple(getattr(result, "items", ()))
        self._update_market_label()
        if errors:
            QMessageBox.warning(
                self,
                "Partial refresh",
                "Refreshed with partial failures:\n  - " + "\n  - ".join(errors),
            )
        else:
            QMessageBox.information(
                self,
                "Prices refreshed",
                f"Fetched {len(items)} items from configured retailers.",
            )

    def _on_refresh_failed(self, message: str) -> None:
        QMessageBox.critical(
            self,
            "Refresh failed",
            f"{message}\n\nCheck retailer API keys in environment variables:\n"
            "  PCA_BESTBUY_API_KEY, PCA_EBAY_CLIENT_ID / _SECRET, ...",
        )

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
        snap = self._controller.state.snapshot
        by_id = {c.id: c for c in (snap.components if snap else ())}
        self._table.setRowCount(len(plan.items))
        for row, it in enumerate(plan.items):
            current = by_id.get(it.replaces_component_id or "")
            self._table.setItem(row, 0, QTableWidgetItem(it.kind.value))
            self._table.setCellWidget(
                row,
                1,
                _make_html_label(
                    _format_upgrade_html(
                        vendor=it.market_item.vendor,
                        model=it.market_item.model,
                        url=it.market_item.url,
                        source=it.market_item.source,
                        replaces_vendor=current.vendor if current else None,
                        replaces_model=current.model if current else None,
                    )
                ),
            )
            price_item = QTableWidgetItem(f"${it.market_item.price_usd:.2f}")
            price_item.setTextAlignment(
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
            )
            self._table.setItem(row, 2, price_item)
            self._table.setCellWidget(
                row, 3, _make_html_label(_format_uplift_html(it.perf_uplift_pct))
            )
            current_specs = dict(current.specs) if current else {}
            new_specs = dict(it.market_item.specs)
            diff_html = render_spec_diff_html(current_specs, new_specs) or (
                "<span style='color:#8a8f9a;'>no detailed specs available</span>"
            )
            self._table.setCellWidget(row, 4, _make_html_label(diff_html))
            rationale_html = (
                f"<div style='line-height:1.45;'>"
                f"{_html.escape(it.rationale) if it.rationale else '<span style=\"color:#8a8f9a;\">-</span>'}"
                f"</div>"
            )
            self._table.setCellWidget(row, 5, _make_html_label(rationale_html))
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
            ["Kind", "Upgrade", "Price (USD)"],
            initial_widths=[80, 520, 120],
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
        snap = self._controller.state.snapshot
        by_id = {c.id: c for c in (snap.components if snap else ())}
        self._table.setRowCount(len(plan.items))
        for row, it in enumerate(plan.items):
            current = by_id.get(it.replaces_component_id or "")
            self._table.setItem(row, 0, QTableWidgetItem(it.kind.value))
            self._table.setCellWidget(
                row,
                1,
                _make_html_label(
                    _format_upgrade_html(
                        vendor=it.market_item.vendor,
                        model=it.market_item.model,
                        url=it.market_item.url,
                        source=it.market_item.source,
                        replaces_vendor=current.vendor if current else None,
                        replaces_model=current.model if current else None,
                    )
                ),
            )
            price_item = QTableWidgetItem(f"${it.market_item.price_usd:.2f}")
            price_item.setTextAlignment(
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
            )
            self._table.setItem(row, 2, price_item)
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

        detect = QAction("&Detect this PC", self)
        detect.setShortcut("Ctrl+D")
        detect.triggered.connect(
            lambda: self._inventory._detect_clicked()
        )
        file_menu.addAction(detect)

        save_snap = QAction("S&ave snapshot as ...", self)
        save_snap.setShortcut(QKeySequence.StandardKey.SaveAs)
        save_snap.triggered.connect(
            lambda: self._inventory._save_clicked()
        )
        file_menu.addAction(save_snap)

        file_menu.addSeparator()

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
        self._recommend._update_market_label()

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
