"""Compatibility graph used by the budget optimizers.

The functions here are pure, side-effect free, and deterministic so they
can be shared between the greedy and ILP optimizers.
"""

from __future__ import annotations

from collections.abc import Iterable

from pca.core.models import (
    BudgetConstraint,
    Component,
    ComponentKind,
    MarketItem,
    SystemSnapshot,
)


def is_compatible(
    snapshot: SystemSnapshot,
    constraint: BudgetConstraint,
    candidate: MarketItem,
    *,
    already_chosen: Iterable[MarketItem] = (),
) -> bool:
    """Return True iff adding ``candidate`` to ``already_chosen`` keeps the rig buildable.

    The rules are intentionally modest for MVP; sophisticated reasoning
    (case clearance, chipset-to-CPU compat) can be layered on without
    breaking the public signature.
    """
    chosen = tuple(already_chosen)

    if _preferred_brand_forbidden(constraint, candidate):
        return False

    effective_socket = _effective_socket(snapshot, chosen, constraint)
    if candidate.kind is ComponentKind.CPU:
        cpu_socket = candidate.specs.get("socket")
        if cpu_socket is not None and effective_socket is not None and cpu_socket != effective_socket:
            return False

    if candidate.kind is ComponentKind.MOTHERBOARD:
        mb_socket = candidate.specs.get("socket")
        mb_ram = candidate.specs.get("ram_type")
        current_cpu = _chosen_or_current(snapshot, chosen, ComponentKind.CPU)
        current_cpu_socket = _spec(current_cpu, "socket") if current_cpu else None
        if (
            mb_socket is not None
            and current_cpu_socket is not None
            and mb_socket != current_cpu_socket
        ):
            return False
        current_ram = _chosen_or_current(snapshot, chosen, ComponentKind.RAM)
        current_ram_type = _spec(current_ram, "type") if current_ram else None
        if (
            mb_ram is not None
            and current_ram_type is not None
            and mb_ram != current_ram_type
        ):
            return False

    if candidate.kind is ComponentKind.RAM:
        ram_type = candidate.specs.get("type")
        mb = _chosen_or_current(snapshot, chosen, ComponentKind.MOTHERBOARD)
        mb_ram = _spec(mb, "ram_type") if mb else None
        if ram_type is not None and mb_ram is not None and ram_type != mb_ram:
            return False

    if constraint.psu_watts_min is not None and candidate.kind is ComponentKind.PSU:
        psu_watts = candidate.specs.get("watts", 0)
        if int(psu_watts) < constraint.psu_watts_min:
            return False

    if constraint.form_factor and candidate.kind in (
        ComponentKind.MOTHERBOARD,
        ComponentKind.CASE,
    ):
        ff = candidate.specs.get("form_factor")
        if ff is not None and ff != constraint.form_factor:
            return False

    return True


def _preferred_brand_forbidden(
    constraint: BudgetConstraint, candidate: MarketItem
) -> bool:
    """Preferred-brand is a soft constraint; never used to reject outright in MVP."""
    del constraint, candidate
    return False


def _effective_socket(
    snapshot: SystemSnapshot,
    chosen: Iterable[MarketItem],
    constraint: BudgetConstraint,
) -> str | None:
    for item in chosen:
        if item.kind is ComponentKind.MOTHERBOARD:
            sk = item.specs.get("socket")
            if isinstance(sk, str):
                return sk
    mb = next(iter(snapshot.components_of(ComponentKind.MOTHERBOARD)), None)
    if mb is not None:
        sk = mb.specs.get("socket")
        if isinstance(sk, str):
            return sk
    return constraint.socket


def _chosen_or_current(
    snapshot: SystemSnapshot,
    chosen: Iterable[MarketItem],
    kind: ComponentKind,
) -> MarketItem | Component | None:
    for item in chosen:
        if item.kind is kind:
            return item
    comps = snapshot.components_of(kind)
    return comps[0] if comps else None


def _spec(obj: MarketItem | Component | None, key: str) -> str | None:
    if obj is None:
        return None
    val = obj.specs.get(key)
    return val if isinstance(val, str) else None


def total_cost(items: Iterable[MarketItem]) -> float:
    return float(sum(float(i.price_usd) for i in items))


def within_budget(items: Iterable[MarketItem], constraint: BudgetConstraint) -> bool:
    return total_cost(items) <= float(constraint.max_usd)
