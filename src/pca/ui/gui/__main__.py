"""``python -m pca.ui.gui`` shim."""

from __future__ import annotations

from pca.ui.gui.app import main

if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
