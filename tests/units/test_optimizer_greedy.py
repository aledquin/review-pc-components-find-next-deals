"""TDD: unit tests for the greedy optimizer.

Red phase first. When implementation catches up, these must all pass.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from pca.budget.constraints import total_cost, within_budget
from pca.budget.optimizer_greedy import optimize_greedy
from pca.core.models import (
    BudgetConstraint,
    ComponentKind,
    Workload,
)
from tests.fixtures import load_market_snapshot, load_rig


@pytest.fixture
def rig_mid():
    return load_rig("rig_mid")


@pytest.fixture
def rig_budget():
    return load_rig("rig_budget")


@pytest.fixture
def catalog_normal():
    items, _ = load_market_snapshot("snapshot_normal")
    return items


@pytest.fixture
def catalog_deals():
    items, _ = load_market_snapshot("snapshot_deal_heavy")
    return items


class TestBasicBehaviour:
    def test_returns_non_empty_plan_when_budget_allows(self, rig_mid, catalog_normal):
        constraint = BudgetConstraint(
            max_usd=Decimal("800"),
            socket="AM4",
            ram_type="DDR4",
            target_workload=Workload.GAMING_1440P,
        )
        plan = optimize_greedy(rig_mid, constraint, catalog_normal)
        assert len(plan.items) >= 1
        assert plan.total_usd <= constraint.max_usd
        assert within_budget([it.market_item for it in plan.items], constraint)

    def test_respects_tight_budget(self, rig_mid, catalog_normal):
        constraint = BudgetConstraint(max_usd=Decimal("100"), socket="AM4", ram_type="DDR4")
        plan = optimize_greedy(rig_mid, constraint, catalog_normal)
        assert plan.total_usd <= Decimal("100")

    def test_empty_catalog_yields_empty_plan(self, rig_mid):
        constraint = BudgetConstraint(max_usd=Decimal("800"))
        plan = optimize_greedy(rig_mid, constraint, [])
        assert plan.items == ()
        assert plan.total_usd == Decimal("0.00")


class TestCompatibility:
    def test_rejects_wrong_socket_cpu(self, rig_mid, catalog_normal):
        """The mid rig is AM4; optimizer must never return an AM5 CPU as a drop-in."""
        constraint = BudgetConstraint(
            max_usd=Decimal("800"),
            socket="AM4",
            ram_type="DDR4",
        )
        plan = optimize_greedy(rig_mid, constraint, catalog_normal)
        cpu_items = [it for it in plan.items if it.kind is ComponentKind.CPU]
        for cpu in cpu_items:
            assert cpu.market_item.specs.get("socket") == "AM4", (
                "optimizer picked incompatible CPU"
            )

    def test_rejects_wrong_ram_type(self, rig_mid, catalog_normal):
        constraint = BudgetConstraint(
            max_usd=Decimal("800"), socket="AM4", ram_type="DDR4"
        )
        plan = optimize_greedy(rig_mid, constraint, catalog_normal)
        ram_items = [it for it in plan.items if it.kind is ComponentKind.RAM]
        for r in ram_items:
            assert r.market_item.specs.get("type") == "DDR4"


class TestDealsImproveOutcome:
    def test_deal_heavy_gives_at_least_as_much_perf(
        self, rig_mid, catalog_normal, catalog_deals
    ):
        """Same budget + strictly lower prices must not reduce total uplift."""
        constraint = BudgetConstraint(
            max_usd=Decimal("500"), socket="AM4", ram_type="DDR4"
        )
        plan_normal = optimize_greedy(rig_mid, constraint, catalog_normal)
        plan_deals = optimize_greedy(rig_mid, constraint, catalog_deals)
        assert plan_deals.overall_perf_uplift_pct >= plan_normal.overall_perf_uplift_pct


class TestDeterminism:
    def test_same_input_same_output(self, rig_mid, catalog_normal):
        constraint = BudgetConstraint(
            max_usd=Decimal("800"), socket="AM4", ram_type="DDR4"
        )
        a = optimize_greedy(rig_mid, constraint, catalog_normal)
        b = optimize_greedy(rig_mid, constraint, catalog_normal)
        assert a == b


class TestPropertyBased:
    """Hypothesis strategies exercise the optimizer against random catalogs."""

    def _constraint(self, budget: float) -> BudgetConstraint:
        return BudgetConstraint(
            max_usd=Decimal(str(round(budget, 2))),
            socket="AM4",
            ram_type="DDR4",
        )

    @pytest.mark.parametrize(
        ("low", "high"),
        [(300.0, 600.0), (600.0, 1500.0), (1500.0, 3000.0)],
    )
    def test_monotonicity_budget_increases_do_not_reduce_perf(
        self, rig_mid, catalog_normal, low, high
    ):
        """More budget must never reduce total perf uplift (greedy is monotone)."""
        lo_plan = optimize_greedy(rig_mid, self._constraint(low), catalog_normal)
        hi_plan = optimize_greedy(rig_mid, self._constraint(high), catalog_normal)
        assert hi_plan.overall_perf_uplift_pct >= lo_plan.overall_perf_uplift_pct

    def test_total_usd_equals_sum_of_prices(self, rig_mid, catalog_normal):
        constraint = BudgetConstraint(
            max_usd=Decimal("800"), socket="AM4", ram_type="DDR4"
        )
        plan = optimize_greedy(rig_mid, constraint, catalog_normal)
        expected = Decimal(str(total_cost(it.market_item for it in plan.items))).quantize(
            Decimal("0.01")
        )
        assert plan.total_usd == expected
