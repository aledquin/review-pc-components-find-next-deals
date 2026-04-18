"""Qt-free controller backing the native GUI.

Kept deliberately widget-free so the unit tests can exercise the same code
paths the window calls, without spinning up a QApplication or a display.
The controller owns the current ``SystemSnapshot`` + ``MarketItem`` tuple
+ any cached deprecations, and offers a small imperative API that the
MainWindow wires up to buttons.
"""

from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # avoid pulling heavy deps at import time
    from pca.market.adapter import AdapterRegistry
    from pca.market.refresh import RefreshResult

from pca.budget.optimizer_greedy import optimize_greedy
from pca.budget.optimizer_ilp import optimize_ilp
from pca.budget.optimizer_multi import optimize_multi
from pca.core.models import (
    BudgetConstraint,
    ComponentKind,
    Deal,
    MarketItem,
    Quote,
    SystemSnapshot,
    UpgradePlan,
    Workload,
)
from pca.core.resources import resource_path
from pca.deprecation.rules import evaluate_all
from pca.inventory.probe import detect_probe
from pca.quoting.builder import build_quote
from pca.reporting.builder import write_quote, write_report


# ---------------------------------------------------------------------------
# OS-native user data dir (% LOCALAPPDATA%/pca on Windows, etc.)
# ---------------------------------------------------------------------------


def user_data_dir() -> Path:
    """Return the per-user data directory we own.

    Honors ``PCA_USER_DATA_DIR`` for tests / portable installs. Otherwise
    picks the OS convention:

    - Windows : ``%LOCALAPPDATA%\\pca``
    - macOS   : ``~/Library/Application Support/pca``
    - Linux   : ``$XDG_DATA_HOME/pca`` or ``~/.local/share/pca``
    """
    override = os.environ.get("PCA_USER_DATA_DIR")
    if override:
        return Path(override)
    if sys.platform.startswith("win"):
        base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~\\AppData\\Local")
        return Path(base) / "pca"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "pca"
    xdg = os.environ.get("XDG_DATA_HOME")
    base = Path(xdg) if xdg else Path.home() / ".local" / "share"
    return base / "pca"


_LAST_SNAPSHOT_NAME = "last_snapshot.json"


@dataclass
class AppState:
    """Mutable state held by the controller."""

    snapshot: SystemSnapshot | None = None
    market_items: tuple[MarketItem, ...] = ()
    deals: tuple[Deal, ...] = ()
    deprecations: tuple[str, ...] = ()
    last_plan: UpgradePlan | None = None
    last_quote: Quote | None = None
    last_errors: list[str] = field(default_factory=list)
    market_generated_at: datetime | None = None
    market_sources: tuple[str, ...] = ()


_STRATEGIES: dict[str, Any] = {
    "greedy": optimize_greedy,
    "ilp": optimize_ilp,
    "multi": optimize_multi,
}


class GuiController:
    """Owns loading + orchestration for the PyQt MainWindow."""

    def __init__(self) -> None:
        self.state = AppState()

    # ---------------- loading ----------------

    def load_snapshot(self, path: Path) -> SystemSnapshot:
        snap = SystemSnapshot.model_validate_json(path.read_text(encoding="utf-8"))
        self.state.snapshot = snap
        self.state.deprecations = tuple(evaluate_all(snap))
        return snap

    def detect_snapshot(self) -> SystemSnapshot:
        """Probe the local machine and cache the result as the active snapshot.

        Uses :func:`pca.inventory.probe.detect_probe` to pick the right OS
        probe (WMI on Windows, ``lshw`` on Linux, ``system_profiler`` on
        macOS). On success the snapshot is also auto-persisted to
        :func:`user_data_dir`/``last_snapshot.json`` so the next launch of
        the GUI can pick up where the user left off.

        Any probe failure propagates unchanged so callers can show a
        meaningful error. This call is synchronous and can take several
        seconds on Windows (WMI queries); GUIs should invoke it from a
        worker thread.
        """
        probe = detect_probe()
        snap = probe.collect()
        self.state.snapshot = snap
        self.state.deprecations = tuple(evaluate_all(snap))
        try:
            target = user_data_dir() / _LAST_SNAPSHOT_NAME
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(snap.model_dump_json(indent=2), encoding="utf-8")
        except OSError:
            # Don't fail the whole detection just because we can't cache.
            pass
        return snap

    def save_snapshot(self, path: Path) -> Path:
        """Persist the currently loaded snapshot to ``path`` as JSON."""
        if self.state.snapshot is None:
            raise RuntimeError("no snapshot to save - load or detect one first")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            self.state.snapshot.model_dump_json(indent=2), encoding="utf-8"
        )
        return path

    def load_last_snapshot(self) -> SystemSnapshot | None:
        """Restore the most recently detected snapshot, if any.

        Called automatically by the GUI at startup. Returns ``None`` when
        the user hasn't run Detect on this machine yet, or when the cache
        file is missing / unreadable.
        """
        path = user_data_dir() / _LAST_SNAPSHOT_NAME
        if not path.is_file():
            return None
        try:
            snap = SystemSnapshot.model_validate_json(
                path.read_text(encoding="utf-8")
            )
        except Exception:
            return None
        self.state.snapshot = snap
        self.state.deprecations = tuple(evaluate_all(snap))
        return snap

    def refresh_market_prices(
        self,
        *,
        registry: "AdapterRegistry | None" = None,
    ) -> "RefreshResult":
        """Query live adapters and replace the in-memory catalog.

        Meant to be called from a Qt worker thread. Returns the raw
        :class:`RefreshResult` so the caller can display partial-success
        warnings, source list, and the new ``generated_at`` timestamp.

        Args:
            registry: Optional adapter registry to use. If ``None`` the
                shared process registry is used - same as the CLI.

        Raises:
            RuntimeError: if no snapshot is loaded.
            MarketError: if no adapters are registered / available.
        """
        from pca.core.config import get_settings
        from pca.market.factory import build_registry_from_settings
        from pca.market.refresh import refresh_market

        if self.state.snapshot is None:
            raise RuntimeError(
                "refresh requires a snapshot - Detect or Load one first"
            )

        reg = (
            registry
            if registry is not None
            else build_registry_from_settings(get_settings())
        )
        result = refresh_market(self.state.snapshot, reg)
        self.state.market_items = result.items
        self.state.deals = result.deals
        self.state.market_generated_at = result.generated_at
        self.state.market_sources = result.sources
        return result

    def load_default_market(
        self,
    ) -> tuple[tuple[MarketItem, ...], tuple[Deal, ...]]:
        """Load the bundled ``resources/market/default_market.json``.

        The default catalog ships with the app so the GUI / web dashboard
        can produce recommendations on first launch without any extra
        user input. Prices are a point-in-time snapshot - refresh with
        the live adapters for current numbers.
        """
        path = resource_path("market", "default_market.json")
        return self.load_market(Path(path))

    def load_market(self, path: Path) -> tuple[tuple[MarketItem, ...], tuple[Deal, ...]]:
        raw = json.loads(path.read_text(encoding="utf-8"))
        items = tuple(MarketItem.model_validate(i) for i in raw.get("items", []))
        deals = tuple(Deal.model_validate(d) for d in raw.get("deals", []))
        self.state.market_items = items
        self.state.deals = deals
        return items, deals

    # ---------------- derived helpers --------

    @staticmethod
    def _socket(snap: SystemSnapshot) -> str | None:
        for kind in (ComponentKind.MOTHERBOARD, ComponentKind.CPU):
            for c in snap.components_of(kind):
                sk = c.specs.get("socket")
                if isinstance(sk, str):
                    return sk
        return None

    @staticmethod
    def _ram_type(snap: SystemSnapshot) -> str | None:
        for c in snap.components_of(ComponentKind.RAM):
            rt = c.specs.get("type")
            if isinstance(rt, str):
                return rt
        return None

    # ---------------- actions ----------------

    def recommend(
        self,
        *,
        budget_usd: Decimal,
        workload: Workload = Workload.GAMING_1440P,
        strategy: str = "greedy",
    ) -> UpgradePlan:
        if self.state.snapshot is None:
            raise RuntimeError("load a snapshot first")
        if not self.state.market_items:
            raise RuntimeError("load a market snapshot first")
        opt = _STRATEGIES.get(strategy, optimize_greedy)
        constraint = BudgetConstraint(
            max_usd=budget_usd,
            socket=self._socket(self.state.snapshot),
            ram_type=self._ram_type(self.state.snapshot),
            target_workload=workload,
        )
        plan = opt(self.state.snapshot, constraint, self.state.market_items)
        self.state.last_plan = plan
        return plan

    def quote(
        self,
        *,
        budget_usd: Decimal,
        workload: Workload = Workload.GAMING_1440P,
        strategy: str = "greedy",
        zip_code: str | None = None,
    ) -> Quote:
        plan = self.recommend(budget_usd=budget_usd, workload=workload, strategy=strategy)
        matching = tuple(
            d
            for d in self.state.deals
            if d.market_item_sku in {it.market_item.sku for it in plan.items}
        )
        q = build_quote(
            plan,
            deals=matching,
            zip_code=zip_code,
            generated_at=datetime.now(UTC),
        )
        self.state.last_quote = q
        return q

    def export_report(self, out_dir: Path) -> Path:
        if self.state.snapshot is None:
            raise RuntimeError("load a snapshot first")
        out_dir.mkdir(parents=True, exist_ok=True)
        r = write_report(
            self.state.snapshot,
            out_dir,
            deprecations=list(self.state.deprecations),
        )
        return Path(r.html_path)

    def export_quote(self, out_dir: Path) -> Path:
        if self.state.last_quote is None:
            raise RuntimeError("generate a quote first")
        if self.state.snapshot is None:
            raise RuntimeError("load a snapshot first")
        out_dir.mkdir(parents=True, exist_ok=True)
        name = (
            f"quote-{self.state.snapshot.id}-"
            f"{int(self.state.last_quote.plan.total_usd)}"
        )
        out = write_quote(self.state.last_quote, out_dir, name=name)
        return Path(out["html_path"])
