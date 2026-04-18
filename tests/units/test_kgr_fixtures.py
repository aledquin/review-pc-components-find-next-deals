"""Sanity-check every KGR fixture parses against the current Pydantic schema.

This catches schema drift between `src/pca/core/models.py` and `tests/data/`
before any downstream test gets to run.
"""

from __future__ import annotations

import pytest

from pca.core.models import ComponentKind
from tests.fixtures import RIG_IDS, SNAPSHOT_IDS, load_market_snapshot, load_rig


@pytest.mark.parametrize("rig_id", RIG_IDS)
def test_rig_parses(rig_id: str) -> None:
    snap = load_rig(rig_id)
    assert snap.id == rig_id
    assert len(snap.components) >= 5
    kinds = {c.kind for c in snap.components}
    required = {
        ComponentKind.CPU,
        ComponentKind.GPU,
        ComponentKind.RAM,
        ComponentKind.MOTHERBOARD,
        ComponentKind.STORAGE,
        ComponentKind.PSU,
    }
    assert required <= kinds, f"rig {rig_id} missing: {required - kinds}"


@pytest.mark.parametrize("snapshot_id", SNAPSHOT_IDS)
def test_market_snapshot_parses(snapshot_id: str) -> None:
    items, deals = load_market_snapshot(snapshot_id)
    assert len(items) >= 10

    skus = {i.sku for i in items}
    assert len(skus) == len(items), "duplicate SKU in snapshot"

    for d in deals:
        assert d.market_item_sku in skus, f"deal references unknown SKU {d.market_item_sku}"


def test_deal_heavy_has_active_deals() -> None:
    _, deals = load_market_snapshot("snapshot_deal_heavy")
    assert len(deals) >= 3


def test_normal_snapshot_has_no_deals() -> None:
    _, deals = load_market_snapshot("snapshot_normal")
    assert deals == ()


def test_every_snapshot_item_has_perf_score() -> None:
    for snapshot_id in SNAPSHOT_IDS:
        items, _ = load_market_snapshot(snapshot_id)
        perf_kinds = {
            ComponentKind.CPU,
            ComponentKind.GPU,
            ComponentKind.RAM,
            ComponentKind.STORAGE,
        }
        for it in items:
            if it.kind in perf_kinds:
                assert it.perf_score is not None and it.perf_score > 0, (
                    f"{snapshot_id}:{it.sku} missing perf_score"
                )
