"""Deprecation rules. Produce a flat list of human-readable warnings.

The logic is deliberately simple so every rule is trivially unit-testable.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from pca.core.models import Component, ComponentKind, SystemSnapshot
from pca.deprecation.catalog import DeprecationCatalog, load_catalog


def evaluate(
    snapshot: SystemSnapshot,
    catalog: DeprecationCatalog | None = None,
    *,
    today: date | None = None,
) -> list[str]:
    """Return deprecation warnings for the snapshot, newest/most severe first."""
    cat = catalog or load_catalog()
    today = today or date.today()
    warnings: list[str] = []

    # Socket rules: check both motherboard and CPU specs for matching IDs.
    socket_index = {e.id: e for e in cat.sockets}
    for comp in snapshot.components:
        sk = _spec(comp.specs, "socket")
        if sk and sk in socket_index:
            entry = socket_index[sk]
            if entry.status == "end_of_life" or (
                entry.end_of_support and entry.end_of_support < today
            ):
                warnings.append(f"{comp.kind.value}: {entry.reason}")

    # Memory generation rules.
    mem_index = {e.id: e for e in cat.memory_generations}
    for ram in snapshot.components_of(ComponentKind.RAM):
        mem_type = _spec(ram.specs, "type")
        if mem_type and mem_type in mem_index:
            entry = mem_index[mem_type]
            if entry.status == "end_of_life":
                warnings.append(f"ram: {entry.reason}")

    # OS rules (match Component.model against the catalog id case-insensitively).
    os_index = {e.id.lower(): e for e in cat.operating_systems}
    for os_comp in snapshot.components_of(ComponentKind.OS):
        key = os_comp.model.lower()
        for os_id, entry in os_index.items():
            if os_id in key:
                if entry.status == "end_of_life" or (
                    entry.end_of_support and entry.end_of_support < today
                ):
                    warnings.append(f"os: {entry.reason}")
                elif entry.status == "nearing_end_of_support":
                    warnings.append(f"os (warning): {entry.reason}")
                break

    return warnings


def _spec(specs: dict[str, Any], key: str) -> str | None:
    val = specs.get(key)
    return val if isinstance(val, str) else None


def gpu_driver_warnings(
    snapshot: SystemSnapshot,
    catalog: DeprecationCatalog | None = None,
    *,
    today: date | None = None,
) -> list[str]:
    """Flag GPUs whose WMI-reported driver_date is older than the max age."""
    cat = catalog or load_catalog()
    today = today or date.today()
    out: list[str] = []
    for gpu in snapshot.components_of(ComponentKind.GPU):
        raw = gpu.specs.get("driver_date")
        if not isinstance(raw, str) or not raw:
            continue
        parsed = _parse_wmi_driver_date(raw)
        if parsed is None:
            continue
        if (today - parsed).days > cat.max_driver_age_days:
            out.append(
                f"gpu: driver for {gpu.vendor} {gpu.model} is "
                f"{(today - parsed).days} days old (update recommended)."
            )
    return out


def _parse_wmi_driver_date(raw: str) -> date | None:
    """Parse WMI's CIM-DATETIME string like ``20240901000000.000000-420``."""
    try:
        return date(int(raw[0:4]), int(raw[4:6]), int(raw[6:8]))
    except (ValueError, IndexError):
        return None


def evaluate_all(
    snapshot: SystemSnapshot,
    catalog: DeprecationCatalog | None = None,
    *,
    today: date | None = None,
) -> list[str]:
    """Convenience: all socket + memory + OS + driver warnings."""
    return [
        *evaluate(snapshot, catalog, today=today),
        *gpu_driver_warnings(snapshot, catalog, today=today),
    ]


def _touch(_: Component) -> None:
    """Make the imported symbol visible for IDEs."""
    del _
