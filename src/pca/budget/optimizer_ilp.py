"""ILP budget optimizer backed by PuLP + CBC.

Formulation:

- One binary variable ``x[sku]`` per catalog item that passes the pre-filter
  (``is_compatible`` against the current snapshot) and whose perf_score is
  strictly greater than the current baseline for its kind.
- Constraints:
    * ``sum(price[sku] * x[sku]) <= budget``
    * ``sum(x[sku] for sku in kind) <= 1`` for every ``ComponentKind`` - we
      never replace a component twice in the same plan.
- Objective:
    * Maximize the per-workload weighted uplift, aggregated per kind.
      Because only one candidate per kind can be chosen, the per-item
      contribution is simply ``weight[kind] * uplift_pct(baseline, candidate)``.

Notes:

- For MVP we do not attempt pairwise compatibility inside the solver (e.g.,
  new CPU forces new motherboard). The pre-filter already screens out
  socket mismatches, and the greedy post-check re-verifies compatibility
  against the winning bundle. Pairwise co-replacement is a v1 enhancement.
- The ``PULP_CBC_CMD`` solver is bundled with PuLP and is MIT-licensed.
"""

from __future__ import annotations

from collections.abc import Iterable
from decimal import Decimal

import pulp

from pca.budget.constraints import is_compatible
from pca.budget.optimizer_greedy import optimize_greedy
from pca.core.models import (
    BudgetConstraint,
    ComponentKind,
    MarketItem,
    SystemSnapshot,
    UpgradeItem,
    UpgradePlan,
)
from pca.gap_analysis.normalize import (
    current_score,
    market_item_score,
    uplift_pct,
    weighted_overall_uplift,
    workload_weights,
)

_PERF_KINDS: tuple[ComponentKind, ...] = (
    ComponentKind.CPU,
    ComponentKind.GPU,
    ComponentKind.RAM,
    ComponentKind.STORAGE,
    ComponentKind.MOTHERBOARD,
    ComponentKind.PSU,
)


def optimize_ilp(
    snapshot: SystemSnapshot,
    constraint: BudgetConstraint,
    catalog: Iterable[MarketItem],
) -> UpgradePlan:
    catalog = tuple(catalog)

    candidates: list[MarketItem] = []
    for item in catalog:
        if item.kind not in _PERF_KINDS:
            continue
        if not is_compatible(snapshot, constraint, item):
            continue
        baseline = current_score(snapshot, item.kind)
        if market_item_score(item) <= baseline:
            continue
        candidates.append(item)

    if not candidates:
        return _empty_plan()

    problem = pulp.LpProblem("pca_upgrade", pulp.LpMaximize)
    x: dict[str, pulp.LpVariable] = {}
    for item in candidates:
        key = _key(item)
        x[key] = pulp.LpVariable(f"pick_{_safe(key)}", cat=pulp.LpBinary)

    weights = workload_weights(constraint.target_workload)
    objective_terms: list[pulp.LpAffineExpression] = []
    for item in candidates:
        baseline = current_score(snapshot, item.kind)
        uplift = uplift_pct(baseline, market_item_score(item))
        weight = weights.get(item.kind, 0.0)
        objective_terms.append(weight * uplift * x[_key(item)])
    problem += pulp.lpSum(objective_terms)

    problem += (
        pulp.lpSum(float(item.price_usd) * x[_key(item)] for item in candidates)
        <= float(constraint.max_usd)
    ), "budget"

    for kind in _PERF_KINDS:
        per_kind = [x[_key(it)] for it in candidates if it.kind is kind]
        if per_kind:
            problem += pulp.lpSum(per_kind) <= 1, f"one_per_{kind.value}"

    solver = pulp.PULP_CBC_CMD(msg=False, timeLimit=10)
    problem.solve(solver)

    if pulp.LpStatus[problem.status] != "Optimal":
        # Fall back to the greedy answer so the caller still receives a plan
        # within the same contract rather than an exception.
        return optimize_greedy(snapshot, constraint, catalog)

    chosen: dict[ComponentKind, MarketItem] = {}
    for item in candidates:
        val = x[_key(item)].value() or 0.0
        if val > 0.5 and item.kind not in chosen:
            chosen[item.kind] = item

    items = tuple(_make_upgrade_item(snapshot, it) for it in _ordered(chosen))
    total = Decimal(
        str(round(sum(float(it.market_item.price_usd) for it in items), 2))
    ).quantize(Decimal("0.01"))
    overall = weighted_overall_uplift(snapshot, chosen, constraint.target_workload)
    return UpgradePlan(
        items=items,
        total_usd=total,
        overall_perf_uplift_pct=overall,
        bottlenecks_resolved=tuple(sorted(k.value for k in chosen)),
        rationale="ilp: maximizes weighted uplift subject to budget",
        strategy="ilp",
    )


def _empty_plan() -> UpgradePlan:
    return UpgradePlan(
        items=(),
        total_usd=Decimal("0.00"),
        overall_perf_uplift_pct=0.0,
        bottlenecks_resolved=(),
        rationale="ilp: no feasible upgrades",
        strategy="ilp",
    )


def _key(item: MarketItem) -> str:
    return f"{item.source}:{item.sku}"


def _safe(s: str) -> str:
    return "".join(ch if ch.isalnum() else "_" for ch in s)


def _ordered(chosen: dict[ComponentKind, MarketItem]) -> Iterable[MarketItem]:
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
    return UpgradeItem(
        replaces_component_id=replaces,
        kind=item.kind,
        market_item=item,
        perf_uplift_pct=round(uplift, 2),
        rationale=(
            f"Replace {item.kind.value} with {item.vendor} {item.model} "
            f"(${item.price_usd:.2f})."
        ),
    )
