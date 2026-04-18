"""US sales-tax estimator stub.

MVP uses a static per-ZIP rate table for a handful of common rates plus a
national average fallback. A real implementation would call TaxJar / Avalara.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

# State-level averaged rate where the ZIP prefix doesn't have a lookup entry.
# Source: combined state+local averages published by the Tax Foundation, 2024.
_STATE_AVG = {
    "CA": Decimal("0.0875"),
    "NY": Decimal("0.0885"),
    "TX": Decimal("0.0820"),
    "WA": Decimal("0.0920"),
    "OR": Decimal("0.0000"),
    "MT": Decimal("0.0000"),
    "NH": Decimal("0.0000"),
    "DE": Decimal("0.0000"),
}

_NATIONAL_AVG = Decimal("0.0745")


def estimate_tax_usd(subtotal_usd: Decimal, *, zip_code: str | None = None) -> Decimal:
    rate = _rate_for_zip(zip_code)
    return (subtotal_usd * rate).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _rate_for_zip(zip_code: str | None) -> Decimal:
    if not zip_code:
        return _NATIONAL_AVG
    prefix = zip_code[:5].strip()
    if not prefix or not prefix.isdigit():
        return _NATIONAL_AVG
    state = _zip_to_state_guess(prefix)
    return _STATE_AVG.get(state, _NATIONAL_AVG)


def _zip_to_state_guess(zip5: str) -> str:
    """Return a very coarse ZIP -> state guess. Good enough for MVP."""
    n = int(zip5)
    if 90000 <= n <= 96699:
        return "CA"
    if 10000 <= n <= 14999:
        return "NY"
    if 75000 <= n <= 79999 or 88500 <= n <= 88599:
        return "TX"
    if 98000 <= n <= 99499:
        return "WA"
    if 97000 <= n <= 97999:
        return "OR"
    if 59000 <= n <= 59999:
        return "MT"
    if 3000 <= n <= 3999:
        return "NH"
    if 19700 <= n <= 19999:
        return "DE"
    return "__national__"
