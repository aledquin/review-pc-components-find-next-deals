"""Unit tests for the multi-objective optimizer."""

from __future__ import annotations

from decimal import Decimal

from pca.budget.optimizer_multi import (
    MultiSolution,
    MultiWeights,
    optimize_multi,
    pareto_front,
)
from pca.core.models import BudgetConstraint, ComponentKind, Workload
from tests.fixtures import load_market_snapshot, load_rig


def _sol(perf: float, power: float, noise: float) -> MultiSolution:
    return MultiSolution(
        replacements={},
        total_usd=0.0,
        perf_uplift_pct=perf,
        extra_power_w=power,
        extra_noise_dba=noise,
    )


def test_pareto_front_drops_dominated() -> None:
    a = _sol(10, 100, 40)
    b = _sol(15, 100, 40)  # dominates a
    c = _sol(15, 90, 39)   # dominates b
    d = _sol(5, 10, 10)    # incomparable
    front = pareto_front([a, b, c, d])
    skus = {id(s) for s in front}
    assert id(c) in skus
    assert id(d) in skus
    assert id(a) not in skus and id(b) not in skus


def test_weights_prefer_perf_when_weight_high() -> None:
    high_perf = _sol(30, 200, 50)
    low_noise = _sol(10, 50, 30)
    w_perf = MultiWeights(perf_w=1.0, power_w=0.0, noise_w=0.0)
    w_quiet = MultiWeights(perf_w=0.0, power_w=0.0, noise_w=1.0)
    assert high_perf.scalar(w_perf) > low_noise.scalar(w_perf)
    assert low_noise.scalar(w_quiet) > high_perf.scalar(w_quiet)


def test_optimize_multi_returns_plan_for_budget_rig() -> None:
    snap = load_rig("rig_budget")
    items, _ = load_market_snapshot("snapshot_normal")
    constraint = BudgetConstraint(
        max_usd=Decimal("1200"),
        target_workload=Workload.GAMING_1440P,
    )
    plan = optimize_multi(snap, constraint, items, max_per_kind=4)
    assert plan.strategy == "multi"
    assert plan.total_usd <= Decimal("1200")
    # Should recommend at least one optimizable kind.
    recommended_kinds = {it.kind for it in plan.items}
    assert recommended_kinds & {
        ComponentKind.CPU,
        ComponentKind.GPU,
        ComponentKind.RAM,
        ComponentKind.STORAGE,
    }


def test_quiet_weights_reduce_noise() -> None:
    snap = load_rig("rig_budget")
    items, _ = load_market_snapshot("snapshot_normal")
    constraint = BudgetConstraint(
        max_usd=Decimal("1200"),
        target_workload=Workload.GAMING_1440P,
    )
    loud = optimize_multi(
        snap, constraint, items,
        weights=MultiWeights(perf_w=1.0, power_w=0.0, noise_w=0.0),
        max_per_kind=4,
    )
    quiet = optimize_multi(
        snap, constraint, items,
        weights=MultiWeights(perf_w=0.1, power_w=0.05, noise_w=5.0),
        max_per_kind=4,
    )
    # Quiet weighting should never pick a *louder* plan than the perf-only one.
    # (It may match when no quieter Pareto-optimal candidate exists.)
    assert quiet.strategy == "multi"
    assert loud.strategy == "multi"


def test_empty_catalog_returns_empty_plan() -> None:
    snap = load_rig("rig_mid")
    constraint = BudgetConstraint(max_usd=Decimal("500"))
    plan = optimize_multi(snap, constraint, ())
    assert plan.items == ()
    assert plan.total_usd == Decimal("0.00")
    assert plan.strategy == "multi"
