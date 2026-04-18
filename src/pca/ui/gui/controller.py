"""Qt-free controller backing the native GUI.

Kept deliberately widget-free so the unit tests can exercise the same code
paths the window calls, without spinning up a QApplication or a display.
The controller owns the current ``SystemSnapshot`` + ``MarketItem`` tuple
+ any cached deprecations, and offers a small imperative API that the
MainWindow wires up to buttons.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

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
from pca.deprecation.rules import evaluate_all
from pca.quoting.builder import build_quote
from pca.reporting.builder import write_quote, write_report


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
