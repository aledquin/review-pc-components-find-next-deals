"""Loader for ``resources/catalogs/deprecation.yaml``."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

import yaml


@dataclass(frozen=True)
class DeprecationEntry:
    id: str
    status: str
    reason: str
    end_of_support: date | None = None


@dataclass(frozen=True)
class DeprecationCatalog:
    sockets: tuple[DeprecationEntry, ...] = ()
    chipsets: tuple[DeprecationEntry, ...] = ()
    memory_generations: tuple[DeprecationEntry, ...] = ()
    operating_systems: tuple[DeprecationEntry, ...] = ()
    max_driver_age_days: int = 365
    source: Path | None = field(default=None, compare=False)


def _parse_entries(raw: list[dict[str, Any]]) -> tuple[DeprecationEntry, ...]:
    out: list[DeprecationEntry] = []
    for r in raw or []:
        out.append(
            DeprecationEntry(
                id=str(r["id"]),
                status=str(r.get("status", "unknown")),
                reason=str(r.get("reason", "")).strip(),
                end_of_support=(
                    _as_date(r.get("end_of_support"))
                    if r.get("end_of_support")
                    else None
                ),
            )
        )
    return tuple(out)


def _as_date(val: Any) -> date:
    if isinstance(val, date):
        return val
    return date.fromisoformat(str(val))


def load_catalog(path: Path | None = None) -> DeprecationCatalog:
    """Load the catalog from YAML. Defaults to the one shipped with the package."""
    if path is None:
        path = (
            Path(__file__).resolve().parents[3]
            / "resources"
            / "catalogs"
            / "deprecation.yaml"
        )
    data: dict[str, Any] = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    drivers = data.get("gpu_drivers") or {}
    return DeprecationCatalog(
        sockets=_parse_entries(data.get("sockets", [])),
        chipsets=_parse_entries(data.get("chipsets", [])),
        memory_generations=_parse_entries(data.get("memory_generations", [])),
        operating_systems=_parse_entries(data.get("operating_systems", [])),
        max_driver_age_days=int(drivers.get("max_driver_age_days", 365)),
        source=path,
    )
