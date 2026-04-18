"""QApplication bootstrap for the native GUI.

Usage:
    pca gui                  # via the Typer CLI
    python -m pca.ui.gui     # bypass the CLI entirely

Optional positional args are forwarded via ``sys.argv`` - the CLI layer is
responsible for pre-loading snapshots/markets when the user passes flags
(handled in ``pca.ui.cli.app``).
"""

from __future__ import annotations

import sys
from pathlib import Path

from pca.ui.gui.controller import GuiController


def main(
    *,
    snapshot_path: Path | None = None,
    market_path: Path | None = None,
) -> int:
    """Start the Qt event loop. Returns the exit code."""
    # Import Qt lazily so ``import pca.ui.gui`` doesn't pull it in when
    # non-GUI commands are used.
    from PyQt6.QtWidgets import QApplication

    from pca.ui.gui.main_window import MainWindow

    controller = GuiController()

    # Auto-restore whatever was there last time the user ran Detect,
    # then let explicit CLI flags override.
    controller.load_last_snapshot()
    try:
        controller.load_default_market()
    except Exception:
        # Bundled market is missing (very old dev tree?). Ignore - the
        # user can still load one via File menu.
        pass

    if snapshot_path is not None:
        controller.load_snapshot(snapshot_path)
    if market_path is not None:
        controller.load_market(market_path)

    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName("PC Upgrade Advisor")
    app.setOrganizationName("PCUpgradeAdvisor")

    window = MainWindow(controller)
    if controller.state.snapshot is not None:
        window._inventory.refresh()
    window.show()

    return int(app.exec())
