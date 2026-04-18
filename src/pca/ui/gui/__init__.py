"""Native Windows/macOS/Linux GUI via PyQt6.

The entry point is :func:`pca.ui.gui.app.main`; the CLI also exposes it as
``pca gui``. Qt-free orchestration lives in :mod:`pca.ui.gui.controller`,
so the bulk of the logic is unit-testable without a display.
"""

from __future__ import annotations

__all__ = ["main"]


def main() -> int:  # pragma: no cover - thin re-export
    from pca.ui.gui.app import main as _main

    return _main()
