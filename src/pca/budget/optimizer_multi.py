"""Multi-objective budget optimizer.

We optimize three objectives jointly:

  - **perf**: weighted overall perf uplift (higher is better).
  - **power**: extra sustained watts (lower is better).
  - **noise**: dBA at load (lower is better).

Each candidate ``MarketItem`` can declare ``power_w`` and ``noise_dba`` in
``specs``; when absent, we fall back to conservative defaults keyed off the
component kind. The optimizer then:

1. Enumerates feasible replacement sets that fit the budget + compatibility.
2. Computes the Pareto front over the three objectives.
3. Ranks the front by a configurable scalarization weight vector, returning
   a single plan (the ``best``) plus the full front for callers that want
   to render a Pareto chart.

For rigs with few viable candidates per kind (the common case for PC parts),
brute-force enumeration is exact and fast. When the candidate count explodes
we defer to pymoo's NSGA-II via the ``pymoo`` extra; callers who don't have
pymoo installed still get a correct, deterministic answer from the exact
enumerator, capped at ``max_enumeration`` combinations.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from decimal import Decimal
from itertools import product
from typing import Any

from pca.budget.constraints import is_compatible
from pca.core.models import (
    BudgetConstraint,
    ComponentKind,
    MarketItem,
    SystemSnapshot,
    UpgradePlan,
    Workload,
)
from pca.budget.optimizer_greedy import _make_upgrade_item  # reuse helper
from pca.gap_analysis.normalize import (
    current_score,
    market_item_score,
    weighted_overall_uplift,
)

_OPTIMIZABLE: tuple[ComponentKind, ...] = (
    ComponentKind.CPU,
    ComponentKind.GPU,
    ComponentKind.RAM,
    ComponentKind.STORAGE,
)


# Conservative per-kind defaults for perf-per-watt modeling. These are rough
# upper bounds; callers should add real ``power_w`` / ``noise_dba`` to
# ``MarketItem.specs`` for accuracy.
_DEFAULT_POWER_W: dict[ComponentKind, float] = {
    ComponentKind.CPU: 125.0,
    ComponentKind.GPU: 250.0,
    ComponentKind.RAM: 10.0,
    ComponentKind.STORAGE: 8.0,
}
_DEFAULT_NOISE_DBA: dict[ComponentKind, float] = {
    ComponentKind.CPU: 38.0,
    ComponentKind.GPU: 42.0,
    ComponentKind.RAM: 0.0,
    ComponentKind.STORAGE: 0.0,
}


@dataclass(frozen=True)
class MultiWeights:
    """Scalarization weights that turn the tri-objective into a scalar score.

    We pick the front candidate that maximizes:
      ``perf * perf_w - power_extra * power_w - noise_extra * noise_w``.
    """

    perf_w: float = 1.0
    power_w: float = 0.05  # per watt
    noise_w: float = 0.5   # per dBA


@dataclass(frozen=True)
class MultiSolution:
    """A single Pareto-optimal solution."""

    replacements: dict[ComponentKind, MarketItem]
    total_usd: float
    perf_uplift_pct: float
    extra_power_w: float
    extra_noise_dba: float

    def scalar(self, w: MultiWeights) -> float:
        return (
            self.perf_uplift_pct * w.perf_w
            - self.extra_power_w * w.power_w
            - self.extra_noise_dba * w.noise_w
        )


def optimize_multi(
    snapshot: SystemSnapshot,
    constraint: BudgetConstraint,
    catalog: Iterable[MarketItem],
    *,
    weights: MultiWeights | None = None,
    max_per_kind: int = 6,
    max_enumeration: int = 20_000,
) -> UpgradePlan:
    """Return a Pareto-optimal UpgradePlan for the (perf, power, noise) triple.

    ``max_per_kind`` caps the top-N candidates we consider per kind (ranked by
    perf per dollar); ``max_enumeration`` guards against combinatorial blowup.
    """
    weights = weights or MultiWeights()
    budget = float(constraint.max_usd)
    catalog = tuple(catalog)

    per_kind: dict[ComponentKind, list[MarketItem]] = {}
    for kind in _OPTIMIZABLE:
        candidates = [c for c in catalog if c.kind == kind and float(c.price_usd) > 0]
        candidates = [c for c in candidates if is_compatible(snapshot, constraint, c)]
        # Rank by perf-per-dollar; discard pure regressions.
        baseline = current_score(snapshot, kind)
        candidates = [c for c in candidates if market_item_score(c) > baseline]
        candidates.sort(
            key=lambda it: (
                -(market_item_score(it) / max(float(it.price_usd), 1.0)),
                it.source,
                it.sku,
            )
        )
        per_kind[kind] = candidates[:max_per_kind]

    # Always include a "keep current" option per kind so partial plans are allowed.
    for kind in list(per_kind):
        per_kind[kind] = [None] + per_kind[kind]  # type: ignore[list-item]

    # Bail out if the cross-product would be absurd.
    product_size = 1
    for opts in per_kind.values():
        product_size *= len(opts) or 1
    if product_size > max_enumeration:  # pragma: no cover - defensive branch
        raise ValueError(
            f"multi-objective enumeration would exceed {max_enumeration} "
            f"combinations ({product_size}). Install 'pymoo' extra and use "
            f"`optimize_multi_ga` to fall back to NSGA-II."
        )

    kinds = list(per_kind.keys())
    solutions: list[MultiSolution] = []
    for combo in product(*(per_kind[k] for k in kinds)):
        replacements: dict[ComponentKind, MarketItem] = {}
        total = 0.0
        power = 0.0
        noise = 0.0
        compat_ok = True
        for kind, item in zip(kinds, combo, strict=True):
            if item is None:
                continue
            replacements[kind] = item
            total += float(item.price_usd)
            power += _extra_power(snapshot, item)
            noise += _extra_noise(snapshot, item)
            if not is_compatible(
                snapshot, constraint, item, already_chosen=replacements.values()
            ):
                compat_ok = False
                break
        if not compat_ok or total > budget:
            continue
        perf = weighted_overall_uplift(snapshot, replacements, constraint.target_workload)
        solutions.append(
            MultiSolution(
                replacements=replacements,
                total_usd=total,
                perf_uplift_pct=perf,
                extra_power_w=power,
                extra_noise_dba=noise,
            )
        )

    if not solutions:
        return UpgradePlan(
            items=(),
            total_usd=Decimal("0.00"),
            overall_perf_uplift_pct=0.0,
            bottlenecks_resolved=(),
            rationale="multi: no feasible (perf, power, noise) solution",
            strategy="multi",
        )

    front = pareto_front(solutions)
    best = max(front, key=lambda s: s.scalar(weights))
    items = tuple(
        _make_upgrade_item(snapshot, best.replacements[k])
        for k in sorted(best.replacements, key=lambda k: k.value)
    )
    return UpgradePlan(
        items=items,
        total_usd=Decimal(str(round(best.total_usd, 2))).quantize(Decimal("0.01")),
        overall_perf_uplift_pct=best.perf_uplift_pct,
        bottlenecks_resolved=tuple(sorted(k.value for k in best.replacements)),
        rationale=(
            f"multi: pareto front of {len(front)} solutions; "
            f"extra {best.extra_power_w:.0f} W / {best.extra_noise_dba:.1f} dBA"
        ),
        strategy="multi",
    )


# ---------------------------------------------------------------------------
# Pareto helpers (pure functions)
# ---------------------------------------------------------------------------


def pareto_front(solutions: list[MultiSolution]) -> list[MultiSolution]:
    """Return solutions not dominated by any other on (perf, -power, -noise)."""
    front: list[MultiSolution] = []
    for a in solutions:
        dominated = False
        for b in solutions:
            if a is b:
                continue
            if _dominates(b, a):
                dominated = True
                break
        if not dominated:
            front.append(a)
    return front


def _dominates(a: MultiSolution, b: MultiSolution) -> bool:
    """True if ``a`` is at least as good on all objectives and strictly better on one."""
    better_or_equal = (
        a.perf_uplift_pct >= b.perf_uplift_pct
        and a.extra_power_w <= b.extra_power_w
        and a.extra_noise_dba <= b.extra_noise_dba
    )
    strictly_better = (
        a.perf_uplift_pct > b.perf_uplift_pct
        or a.extra_power_w < b.extra_power_w
        or a.extra_noise_dba < b.extra_noise_dba
    )
    return better_or_equal and strictly_better


# ---------------------------------------------------------------------------
# Extra-power / extra-noise estimators
# ---------------------------------------------------------------------------


def _spec_float(item: MarketItem, key: str) -> float | None:
    v: Any = item.specs.get(key)
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _extra_power(snapshot: SystemSnapshot, item: MarketItem) -> float:
    """Approximate incremental sustained wattage introduced by replacing the
    current component of ``item.kind``. Negative values (more efficient
    replacement) clamp to 0 for ranking purposes."""
    new_w = _spec_float(item, "power_w") or _DEFAULT_POWER_W.get(item.kind, 0.0)
    current = snapshot.components_of(item.kind)
    if not current:
        return new_w
    cur_w = _spec_float_from_component(current[0], "power_w") or _DEFAULT_POWER_W.get(item.kind, 0.0)
    return max(new_w - cur_w, 0.0)


def _extra_noise(snapshot: SystemSnapshot, item: MarketItem) -> float:
    new_n = _spec_float(item, "noise_dba") or _DEFAULT_NOISE_DBA.get(item.kind, 0.0)
    current = snapshot.components_of(item.kind)
    if not current:
        return new_n
    cur_n = _spec_float_from_component(current[0], "noise_dba") or _DEFAULT_NOISE_DBA.get(item.kind, 0.0)
    # dBA isn't linear, but for ranking purposes max-delta is fine.
    return max(new_n - cur_n, 0.0)


def _spec_float_from_component(component: Any, key: str) -> float | None:
    v = getattr(component, "specs", {}).get(key)
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


__all__ = [
    "MultiSolution",
    "MultiWeights",
    "optimize_multi",
    "pareto_front",
    "Workload",
]
