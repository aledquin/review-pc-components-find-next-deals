"""US sales-tax estimator.

Resolves a USPS ZIP-5 to an averaged state + local rate using the catalog at
``resources/catalogs/us_tax_rates.yaml``. The catalog is the single source of
truth; the legacy hard-coded fallback only runs when the file is missing
(e.g. in a trimmed wheel). Real tax calculation belongs to a live API
(TaxJar, Avalara) - see ``docs/data-sources-tos.md``.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from pca.core.resources import resource_path


def _catalog_path() -> Path:
    return resource_path("catalogs", "us_tax_rates.yaml")


@lru_cache(maxsize=1)
def _catalog() -> dict[str, Any]:
    path = _catalog_path()
    if not path.exists():  # pragma: no cover - ships inside resources/
        return _FALLBACK_CATALOG
    with path.open("r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    if not isinstance(data, dict):
        return _FALLBACK_CATALOG
    return data


def estimate_tax_usd(subtotal_usd: Decimal, *, zip_code: str | None = None) -> Decimal:
    """Return the estimated sales tax in USD, rounded to the cent."""
    rate = _rate_for_zip(zip_code)
    return (subtotal_usd * rate).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def state_for_zip(zip_code: str | None) -> str | None:
    """Return the USPS state code for ``zip_code`` or None if unresolved."""
    if not zip_code:
        return None
    prefix = zip_code[:5].strip()
    if len(prefix) != 5 or not prefix.isdigit():
        return None
    n = int(prefix)
    for entry in _catalog().get("zip_ranges", []):
        lo, hi, state = entry
        lo_i = int(str(lo).lstrip("0") or "0")
        hi_i = int(str(hi).lstrip("0") or "0")
        if lo_i <= n <= hi_i:
            return str(state)
    return None


def _rate_for_zip(zip_code: str | None) -> Decimal:
    national = Decimal(str(_catalog().get("national_average", "0.0745")))
    state = state_for_zip(zip_code)
    if state is None:
        return national
    states = _catalog().get("states", {})
    if state not in states:
        return national
    return Decimal(str(states[state]))


def clear_cache() -> None:
    """Used by tests after mutating the catalog path."""
    _catalog.cache_clear()


# Minimal embedded fallback so the cache loader is resilient if the YAML file
# is trimmed from a wheel. Keep these rates conservative.
_FALLBACK_CATALOG: dict[str, Any] = {
    "national_average": 0.0745,
    "states": {
        "CA": 0.0875,
        "NY": 0.0885,
        "TX": 0.0820,
        "WA": 0.0920,
        "OR": 0.0,
        "MT": 0.0,
        "NH": 0.0,
        "DE": 0.0,
    },
    "zip_ranges": [
        [90000, 96699, "CA"],
        [10000, 14999, "NY"],
        [75000, 79999, "TX"],
        [98000, 99499, "WA"],
        [97000, 97999, "OR"],
        [59000, 59999, "MT"],
        [3000, 3999, "NH"],
        [19700, 19999, "DE"],
    ],
}
