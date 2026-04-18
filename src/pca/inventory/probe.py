"""``InventoryProbe`` protocol and a factory that dispatches by OS.

The protocol is deliberately small: one call returns a fully populated
``SystemSnapshot``. Probes may internally use multiple sub-probes.
"""

from __future__ import annotations

import platform
import uuid
from datetime import UTC, datetime
from typing import Protocol

from pca.core.errors import InventoryError
from pca.core.models import SystemSnapshot


class InventoryProbe(Protocol):
    """Any object that can inspect the current host and return a snapshot."""

    def collect(self) -> SystemSnapshot: ...


def detect_probe() -> InventoryProbe:
    """Return the best probe for the current OS.

    Raises ``InventoryError`` if the host is unsupported and falls back to
    the ``StubProbe`` when native imports fail so that the CLI still runs.
    """
    system = platform.system()
    if system == "Windows":
        try:
            from pca.inventory.windows import WindowsInventoryProbe

            return WindowsInventoryProbe()
        except Exception as exc:  # pragma: no cover - only on missing deps
            raise InventoryError(
                "Windows inventory probe is unavailable. "
                "Install the 'windows' extra: pip install pc-upgrade-advisor[windows]."
            ) from exc
    if system == "Linux":
        from pca.inventory.linux import LinuxInventoryProbe

        return LinuxInventoryProbe()
    if system == "Darwin":
        from pca.inventory.macos import MacosInventoryProbe

        return MacosInventoryProbe()
    raise InventoryError(f"Unsupported operating system: {system}")


def new_snapshot_id() -> str:
    """Return a fresh snapshot identifier."""
    return f"snap-{uuid.uuid4().hex[:12]}"


def now_utc() -> datetime:
    """Return a timezone-aware UTC now(). Separate so tests can monkeypatch."""
    return datetime.now(UTC)
