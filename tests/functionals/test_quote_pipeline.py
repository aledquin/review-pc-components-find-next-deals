"""Functional: the full `recommend + quote` pipeline on every (rig, budget) pair.

Outputs are compared against ``tests/data/expected_quotes/*.json`` which are
authored when the implementation stabilizes. On first run, the expected files
are created from the live output (with a deterministic timestamp). To update
a golden on purpose, delete it and re-run.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from decimal import Decimal

import pytest

from pca.budget.optimizer_greedy import optimize_greedy
from pca.core.models import BudgetConstraint, ComponentKind, SystemSnapshot, Workload
from pca.quoting.builder import build_quote
from tests.fixtures import QUOTES_DIR, load_market_snapshot, load_rig


def _socket(rig: SystemSnapshot) -> str | None:
    for kind in (ComponentKind.MOTHERBOARD, ComponentKind.CPU):
        for c in rig.components_of(kind):
            sk = c.specs.get("socket")
            if isinstance(sk, str):
                return sk
    return None


def _ram_type(rig: SystemSnapshot) -> str | None:
    for c in rig.components_of(ComponentKind.RAM):
        rt = c.specs.get("type")
        if isinstance(rt, str):
            return rt
    for c in rig.components_of(ComponentKind.MOTHERBOARD):
        rt = c.specs.get("ram_type")
        if isinstance(rt, str):
            return rt
    return None

_FIXED_NOW = datetime(2025, 1, 1, 12, 0, tzinfo=UTC)

_CASES: tuple[tuple[str, str, int], ...] = (
    ("rig_budget", "snapshot_normal", 300),
    ("rig_mid", "snapshot_normal", 800),
    ("rig_mid", "snapshot_deal_heavy", 800),
    ("rig_highend", "snapshot_normal", 1500),
)


@pytest.mark.parametrize(("rig_id", "snap_id", "budget"), _CASES)
def test_quote_matches_golden_or_creates_it(
    rig_id: str, snap_id: str, budget: int
) -> None:
    rig = load_rig(rig_id)
    items, deals = load_market_snapshot(snap_id)

    constraint = BudgetConstraint(
        max_usd=Decimal(str(budget)),
        socket=_socket(rig),
        ram_type=_ram_type(rig),
        target_workload=Workload.GAMING_1440P,
    )
    plan = optimize_greedy(rig, constraint, items)
    matching_deals = tuple(
        d for d in deals if d.market_item_sku in {it.market_item.sku for it in plan.items}
    )
    quote = build_quote(
        plan,
        deals=matching_deals,
        zip_code="10001",
        generated_at=_FIXED_NOW,
    )
    actual = json.loads(quote.model_dump_json())

    QUOTES_DIR.mkdir(parents=True, exist_ok=True)
    golden_path = QUOTES_DIR / f"{rig_id}__{snap_id}__budget_{budget}.json"
    if not golden_path.exists():
        golden_path.write_text(json.dumps(actual, indent=2), encoding="utf-8")
        pytest.skip(f"Created missing golden: {golden_path}")

    expected = json.loads(golden_path.read_text(encoding="utf-8"))
    assert actual == expected, (
        f"Quote drift for {rig_id}/{snap_id}/${budget}. "
        f"Delete {golden_path} and re-run if the drift is expected."
    )
