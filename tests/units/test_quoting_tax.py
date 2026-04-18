"""Unit tests for the YAML-backed US sales-tax estimator."""

from __future__ import annotations

from decimal import Decimal

import pytest

from pca.quoting.tax import clear_cache, estimate_tax_usd, state_for_zip


@pytest.fixture(autouse=True)
def _flush_cache() -> None:
    clear_cache()


@pytest.mark.parametrize(
    ("zip_code", "state"),
    [
        ("10001", "NY"),   # NYC
        ("94105", "CA"),   # San Francisco
        ("78701", "TX"),   # Austin
        ("98101", "WA"),   # Seattle
        ("97201", "OR"),   # Portland (0% sales tax)
        ("03301", "NH"),   # Concord
        ("19901", "DE"),   # Dover
        ("06010", "CT"),   # Bristol (leading zero)
        ("00501", "NY"),   # Holtsville
    ],
)
def test_state_for_zip_happy_path(zip_code: str, state: str) -> None:
    assert state_for_zip(zip_code) == state


@pytest.mark.parametrize("bad", [None, "", "abc12", "1234"])
def test_state_for_zip_rejects_malformed(bad: str | None) -> None:
    assert state_for_zip(bad) is None


def test_oregon_is_zero_rate() -> None:
    assert estimate_tax_usd(Decimal("1000"), zip_code="97201") == Decimal("0.00")


def test_california_rate_is_positive() -> None:
    tax = estimate_tax_usd(Decimal("1000"), zip_code="94105")
    assert tax > Decimal("0")
    assert tax <= Decimal("100"), f"suspicious CA rate: {tax}"


def test_unknown_zip_falls_back_to_national() -> None:
    # ZIP 00100 is unassigned; it should fall through every range.
    tax_unknown = estimate_tax_usd(Decimal("1000"), zip_code="00100")
    tax_none = estimate_tax_usd(Decimal("1000"), zip_code=None)
    assert tax_unknown == tax_none


def test_rounding_is_half_up_to_cents() -> None:
    tax = estimate_tax_usd(Decimal("123.456"), zip_code="10001")
    assert tax == tax.quantize(Decimal("0.01"))
