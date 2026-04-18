"""Top-level pytest configuration shared by all test suites."""

from __future__ import annotations

import sys
from pathlib import Path

# Make `src/` importable without an editable install (useful when CI fresh-clones).
_SRC = Path(__file__).resolve().parents[1] / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))
