"""Driver-age helpers. Re-exports the GPU check from ``rules`` for clarity."""

from __future__ import annotations

from pca.deprecation.rules import gpu_driver_warnings

__all__ = ["gpu_driver_warnings"]
