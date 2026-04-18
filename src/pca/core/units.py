"""Unit helpers for currency, storage, bandwidth, power, and noise.

Kept tiny and dependency-free so it is safe to import everywhere.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal
from typing import Final

USD: Final[str] = "USD"


def to_cents(usd: Decimal | float | int | str) -> int:
    """Convert a USD amount to integer cents using banker's-safe rounding."""
    return int(Decimal(str(usd)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP) * 100)


def from_cents(cents: int) -> Decimal:
    """Convert integer cents back to a Decimal USD value."""
    return (Decimal(cents) / Decimal(100)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def gib_to_gb(gib: float) -> float:
    """Convert binary gibibytes to decimal gigabytes."""
    return gib * (1024**3) / (1000**3)


def gb_to_gib(gb: float) -> float:
    """Convert decimal gigabytes to binary gibibytes."""
    return gb * (1000**3) / (1024**3)


def format_usd(value: Decimal | float | int) -> str:
    """Format a USD amount as ``$1,234.56``."""
    d = Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return f"${d:,.2f}"
