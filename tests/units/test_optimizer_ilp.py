"""TDD: unit tests for the ILP optimizer. Parallels test_optimizer_greedy."""

from __future__ import annotations

from decimal import Decimal

import pytest

from pca.budget.optimizer_greedy import optimize_greedy
from pca.budget.optimizer_ilp import optimize_ilp
from pca.core.models import BudgetConstraint, ComponentKind, Workload
from tests.fixtures import load_market_snapshot, load_rig


@pytest.fixture
def rig_mid():
    return load_rig("rig_mid")


@pytest.fixture
def catalog_normal():
    items, _ = load_market_snapshot("snapshot_normal")
    return items


class TestIlpBasics:
    def test_respects_budget(self, rig_mid, catalog_normal):
        constraint = BudgetConstraint(
            max_usd=Decimal("800"),
            socket="AM4",
            ram_type="DDR4",
            target_workload=Workload.GAMING_1440P,
        )
        plan = optimize_ilp(rig_mid, constraint, catalog_normal)
        assert plan.total_usd <= constraint.max_usd

    def test_no_socket_mismatch(self, rig_mid, catalog_normal):
        constraint = BudgetConstraint(
            max_usd=Decimal("800"), socket="AM4", ram_type="DDR4"
        )
        plan = optimize_ilp(rig_mid, constraint, catalog_normal)
        for it in plan.items:
            if it.kind is ComponentKind.CPU:
                assert it.market_item.specs.get("socket") == "AM4"

    def test_strategy_label(self, rig_mid, catalog_normal):
        constraint = BudgetConstraint(
            max_usd=Decimal("800"), socket="AM4", ram_type="DDR4"
        )
        plan = optimize_ilp(rig_mid, constraint, catalog_normal)
        assert plan.strategy == "ilp"


class TestIlpVsGreedy:
    """ILP is optimal; it must meet or beat greedy on the same input."""

    def test_ilp_at_least_as_good_as_greedy(self, rig_mid, catalog_normal):
        constraint = BudgetConstraint(
            max_usd=Decimal("800"),
            socket="AM4",
            ram_type="DDR4",
            target_workload=Workload.GAMING_1440P,
        )
        greedy = optimize_greedy(rig_mid, constraint, catalog_normal)
        ilp = optimize_ilp(rig_mid, constraint, catalog_normal)
        assert ilp.overall_perf_uplift_pct >= greedy.overall_perf_uplift_pct - 1e-6
