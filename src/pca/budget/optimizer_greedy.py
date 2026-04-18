"""Greedy budget optimizer.

Strategy:

1. For every candidate in the catalog that beats the current component of the
   same ``ComponentKind`` and passes the compatibility graph, compute
   ``uplift_per_dollar = weighted_uplift / price``.
2. Sort candidates by that ratio, descending. Ties are broken by
   ``(-perf_score, kind.value, sku)`` so golden files stay stable.
3. Walk the sorted list; accept the first candidate per kind that keeps the
   running total below the budget and remains compatible with everything
   already chosen. Reject later candidates of the same kind.
4. Stop when the budget is exhausted or the candidate list is done.

The greedy algorithm is not optimal, but it is O(n log n), deterministic,
and monotone with respect to budget, which is exactly what the unit tests
assert.
"""

from __future__ import annotations

from collections.abc import Iterable
from decimal import Decimal

from pca.budget.constraints import is_compatible
from pca.core.models import (
    BudgetConstraint,
    ComponentKind,
    MarketItem,
    SystemSnapshot,
    UpgradeItem,
    UpgradePlan,
    Workload,
)
from pca.gap_analysis.normalize import (
    current_score,
    market_item_score,
    uplift_pct,
    weighted_overall_uplift,
)

_PERF_KINDS: tuple[ComponentKind, ...] = (
    ComponentKind.CPU,
    ComponentKind.GPU,
    ComponentKind.RAM,
    ComponentKind.STORAGE,
    ComponentKind.MOTHERBOARD,
    ComponentKind.PSU,
)


def optimize_greedy(
    snapshot: SystemSnapshot,
    constraint: BudgetConstraint,
    catalog: Iterable[MarketItem],
) -> UpgradePlan:
    workload = constraint.target_workload
    catalog = tuple(catalog)

    scored: list[tuple[float, float, MarketItem]] = []
    for item in catalog:
        if item.kind not in _PERF_KINDS:
            continue
        if not is_compatible(snapshot, constraint, item):
            continue
        if float(item.price_usd) <= 0:
            continue

        baseline = current_score(snapshot, item.kind)
        candidate_score = market_item_score(item)
        if candidate_score <= baseline:
            continue

        uplift = uplift_pct(baseline, candidate_score)
        ratio = uplift / float(item.price_usd)
        scored.append((ratio, candidate_score, item))

    scored.sort(
        key=lambda t: (-t[0], -t[1], t[2].kind.value, t[2].source, t[2].sku),
    )

    chosen: dict[ComponentKind, MarketItem] = {}
    running_total = 0.0
    for _ratio, _score, item in scored:
        if item.kind in chosen:
            continue
        prospective = running_total + float(item.price_usd)
        if prospective > float(constraint.max_usd):
            continue
        if not is_compatible(
            snapshot, constraint, item, already_chosen=chosen.values()
        ):
            continue
        chosen[item.kind] = item
        running_total = prospective

    items = tuple(_make_upgrade_item(snapshot, it) for it in _ordered(chosen))
    total = Decimal(str(round(running_total, 2))).quantize(Decimal("0.01"))
    overall = weighted_overall_uplift(snapshot, chosen, workload)
    return UpgradePlan(
        items=items,
        total_usd=total,
        overall_perf_uplift_pct=overall,
        bottlenecks_resolved=tuple(sorted(k.value for k in chosen)),
        rationale="greedy: perf-per-dollar, one swap per component kind",
        strategy="greedy",
    )


def _ordered(chosen: dict[ComponentKind, MarketItem]) -> Iterable[MarketItem]:
    """Return chosen items in a stable kind order for deterministic golden files."""
    order = {k: i for i, k in enumerate(_PERF_KINDS)}
    return sorted(
        chosen.values(),
        key=lambda it: (order.get(it.kind, 99), it.source, it.sku),
    )


def _make_upgrade_item(snapshot: SystemSnapshot, item: MarketItem) -> UpgradeItem:
    current = snapshot.components_of(item.kind)
    replaces = current[0].id if current else None
    baseline = current_score(snapshot, item.kind)
    uplift = uplift_pct(baseline, market_item_score(item))
    rationale = _rationale(item, baseline, market_item_score(item))
    return UpgradeItem(
        replaces_component_id=replaces,
        kind=item.kind,
        market_item=item,
        perf_uplift_pct=round(uplift, 2),
        rationale=rationale,
    )


def _rationale(item: MarketItem, baseline: float, score: float) -> str:
    workload_hint = "balances perf vs. cost"
    if item.kind is ComponentKind.GPU and score >= 2 * max(baseline, 1.0):
        workload_hint = "major bottleneck removed"
    elif item.kind is ComponentKind.CPU and score >= 1.5 * max(baseline, 1.0):
        workload_hint = "eliminates CPU bottleneck"
    elif item.kind is ComponentKind.STORAGE:
        workload_hint = "reduces load times and random-I/O waits"
    return (
        f"Replace {item.kind.value} with {item.vendor} {item.model} "
        f"(${item.price_usd:.2f}): {workload_hint}."
    )


__all__ = ["optimize_greedy", "Workload"]
