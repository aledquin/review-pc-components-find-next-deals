"""Perf-score normalization and replacement-value math.

These helpers are deliberately small and deterministic so the greedy and ILP
optimizers can reuse them without pulling in heavier dependencies.
"""

from __future__ import annotations

from pca.core.models import (
    Benchmark,
    Component,
    ComponentKind,
    MarketItem,
    SystemSnapshot,
    Workload,
)

# Catalog scores for a handful of components we expect to see in the reference
# rigs. Values are indexed against ``Ryzen 7 5800X3D == 1000`` for CPUs and
# against the catalog entries in ``tests/data/market_snapshots/`` for GPUs,
# RAM, and storage. Tests that need new entries must add them here.
_CATALOG_SCORE: dict[tuple[ComponentKind, str, str], float] = {
    (ComponentKind.CPU, "Intel", "Core i5-8400"): 420.0,
    (ComponentKind.CPU, "AMD", "Ryzen 5 3600"): 680.0,
    (ComponentKind.CPU, "AMD", "Ryzen 7 7800X3D"): 1400.0,
    (ComponentKind.GPU, "NVIDIA", "GeForce GTX 1060 6GB"): 280.0,
    (ComponentKind.GPU, "NVIDIA", "GeForce RTX 2060 Super"): 680.0,
    (ComponentKind.GPU, "NVIDIA", "GeForce RTX 4080"): 2200.0,
    (ComponentKind.RAM, "Corsair", "Vengeance LPX 2x8GB DDR4-2666"): 140.0,
    (ComponentKind.RAM, "G.Skill", "Ripjaws V 2x8GB DDR4-3200"): 190.0,
    (ComponentKind.RAM, "G.Skill", "Trident Z5 2x16GB DDR5-6000"): 360.0,
    (ComponentKind.STORAGE, "Kingston", "A400 480GB"): 40.0,
    (ComponentKind.STORAGE, "Samsung", "970 EVO 1TB"): 500.0,
    (ComponentKind.STORAGE, "Samsung", "990 Pro 2TB"): 1000.0,
}

# Default per-workload weights used when we roll up per-component uplifts
# into a single overall figure. Tests pin these via the ``Workload`` enum.
_WORKLOAD_WEIGHTS: dict[Workload, dict[ComponentKind, float]] = {
    Workload.GAMING_1080P: {
        ComponentKind.CPU: 0.45,
        ComponentKind.GPU: 0.40,
        ComponentKind.RAM: 0.10,
        ComponentKind.STORAGE: 0.05,
    },
    Workload.GAMING_1440P: {
        ComponentKind.CPU: 0.30,
        ComponentKind.GPU: 0.55,
        ComponentKind.RAM: 0.10,
        ComponentKind.STORAGE: 0.05,
    },
    Workload.GAMING_4K: {
        ComponentKind.CPU: 0.20,
        ComponentKind.GPU: 0.65,
        ComponentKind.RAM: 0.10,
        ComponentKind.STORAGE: 0.05,
    },
    Workload.PRODUCTIVITY: {
        ComponentKind.CPU: 0.50,
        ComponentKind.GPU: 0.10,
        ComponentKind.RAM: 0.25,
        ComponentKind.STORAGE: 0.15,
    },
    Workload.CONTENT_CREATION: {
        ComponentKind.CPU: 0.40,
        ComponentKind.GPU: 0.35,
        ComponentKind.RAM: 0.15,
        ComponentKind.STORAGE: 0.10,
    },
    Workload.ML_WORKSTATION: {
        ComponentKind.CPU: 0.20,
        ComponentKind.GPU: 0.55,
        ComponentKind.RAM: 0.15,
        ComponentKind.STORAGE: 0.10,
    },
}


def component_score(component: Component, benchmarks: tuple[Benchmark, ...] = ()) -> float:
    """Blend catalog score (70%) with measured benchmarks (30%) when available."""
    catalog = _CATALOG_SCORE.get((component.kind, component.vendor, component.model))
    measured = _measured_score(component, benchmarks)
    if catalog is None and measured is None:
        return 0.0
    if catalog is None:
        return float(measured or 0.0)
    if measured is None:
        return catalog
    return 0.7 * measured + 0.3 * catalog


def _measured_score(
    component: Component, benchmarks: tuple[Benchmark, ...]
) -> float | None:
    relevant = [b for b in benchmarks if b.component_id == component.id]
    if not relevant:
        return None
    # A cheap mapping from raw units to a catalog-comparable magnitude. Not
    # exact; the intent is only to keep measured vs catalog within an order
    # of magnitude so the 70/30 blend is meaningful.
    scale = {
        ComponentKind.CPU: 1.0 / 10.0,
        ComponentKind.GPU: 1.0,
        ComponentKind.RAM: 1.0,
        ComponentKind.STORAGE: 1.0 / 1000.0,
    }.get(component.kind, 1.0)
    return max(b.value for b in relevant) * scale


def market_item_score(item: MarketItem) -> float:
    """Prefer the explicit ``perf_score`` on the item; fall back to catalog."""
    if item.perf_score is not None:
        return float(item.perf_score)
    return _CATALOG_SCORE.get((item.kind, item.vendor, item.model), 0.0)


def current_score(snapshot: SystemSnapshot, kind: ComponentKind) -> float:
    comps = snapshot.components_of(kind)
    if not comps:
        return 0.0
    return component_score(comps[0], snapshot.benchmarks)


def uplift_pct(from_score: float, to_score: float) -> float:
    """Percent improvement; safe on zero baselines."""
    if from_score <= 0:
        return 100.0 if to_score > 0 else 0.0
    return max(0.0, 100.0 * (to_score - from_score) / from_score)


def workload_weights(workload: Workload) -> dict[ComponentKind, float]:
    """Return a copy of the per-component weights for ``workload``."""
    return dict(_WORKLOAD_WEIGHTS[workload])


def weighted_overall_uplift(
    snapshot: SystemSnapshot,
    replacements: dict[ComponentKind, MarketItem],
    workload: Workload,
) -> float:
    """Return the weighted overall uplift for a candidate replacement set."""
    weights = _WORKLOAD_WEIGHTS[workload]
    total = 0.0
    for kind, weight in weights.items():
        from_score = current_score(snapshot, kind)
        item = replacements.get(kind)
        to_score = market_item_score(item) if item is not None else from_score
        total += weight * uplift_pct(from_score, to_score)
    return round(total, 4)
