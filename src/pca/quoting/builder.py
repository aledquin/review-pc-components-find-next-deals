"""Assemble an :class:`UpgradePlan` into a final :class:`Quote`."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal

from pca.core.models import Deal, Quote, UpgradePlan
from pca.quoting.tax import estimate_tax_usd


def _round_usd(v: Decimal) -> Decimal:
    return v.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def estimate_shipping_usd(subtotal_usd: Decimal) -> Decimal:
    """Very rough shipping model: free above $99, else a flat $9.99."""
    if subtotal_usd >= Decimal("99.00"):
        return Decimal("0.00")
    return Decimal("9.99")


def build_quote(
    plan: UpgradePlan,
    *,
    deals: tuple[Deal, ...] = (),
    zip_code: str | None = None,
    generated_at: datetime | None = None,
) -> Quote:
    """Return a :class:`Quote` with estimated tax + shipping added."""
    subtotal = plan.total_usd
    tax = estimate_tax_usd(subtotal, zip_code=zip_code)
    shipping = estimate_shipping_usd(subtotal)
    grand_total = _round_usd(subtotal + tax + shipping)
    return Quote(
        plan=plan,
        tax_usd=tax,
        shipping_usd=shipping,
        grand_total_usd=grand_total,
        generated_at=generated_at or datetime.now(UTC),
        deals=deals,
    )
