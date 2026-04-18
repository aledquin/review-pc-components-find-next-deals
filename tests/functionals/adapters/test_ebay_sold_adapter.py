"""Contract + stats tests for the eBay sold-listings adapter."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

import pytest

from pca.core.models import ComponentKind
from pca.market.adapters.ebay_sold import EbaySoldAdapter


def _canned_sold(prices: list[float]) -> dict[str, Any]:
    return {
        "itemSales": [
            {
                "itemId": f"v1|{i:06d}|0",
                "title": f"Used RTX 3080 #{i}",
                "lastSoldPrice": {"value": f"{p:.2f}", "currency": "USD"},
                "lastSoldDate": "2026-04-01T12:00:00Z",
                "condition": "Used",
                "seller": {"username": f"seller{i}"},
                "itemWebUrl": f"https://www.ebay.com/itm/{i}",
            }
            for i, p in enumerate(prices, start=1)
        ]
    }


def test_unavailable_without_credentials() -> None:
    a = EbaySoldAdapter(None, None, transport=lambda p, q: {})
    assert a.is_available() is False
    assert list(a.search(ComponentKind.GPU, "rtx 3080")) == []


def test_search_returns_out_of_stock_items() -> None:
    def fake(path: str, params: dict[str, Any]) -> dict[str, Any]:
        assert path.endswith("/item_sales/search")
        return _canned_sold([500.0, 520.0, 480.0])

    a = EbaySoldAdapter("cid", "secret", transport=fake)
    items = list(a.search(ComponentKind.GPU, "rtx 3080"))
    assert len(items) == 3
    assert items[0].sku.startswith("EBAYSOLD-")
    assert all(i.source == "ebay-sold" for i in items)


def test_sold_price_stats_median_matches_expectation() -> None:
    prices = [400.0, 420.0, 450.0, 475.0, 500.0, 520.0, 550.0]

    def fake(path: str, params: dict[str, Any]) -> dict[str, Any]:
        return _canned_sold(prices)

    a = EbaySoldAdapter("cid", "secret", transport=fake)
    stats = a.sold_price_stats(ComponentKind.GPU, "rtx 3080")
    assert stats is not None
    assert stats.sample_size == len(prices)
    assert stats.p25_usd <= stats.median_usd <= stats.p75_usd
    assert stats.median_usd == Decimal("475.00")


def test_sold_price_stats_returns_none_when_sample_too_small() -> None:
    def fake(path: str, params: dict[str, Any]) -> dict[str, Any]:
        return _canned_sold([500.0, 520.0])

    a = EbaySoldAdapter("cid", "secret", transport=fake)
    assert a.sold_price_stats(ComponentKind.GPU, "rtx 3080") is None


def test_fetch_by_sku_always_none() -> None:
    a = EbaySoldAdapter("cid", "secret", transport=lambda p, q: {})
    assert a.fetch_by_sku("EBAYSOLD-anything") is None


def test_active_deals_always_empty() -> None:
    a = EbaySoldAdapter("cid", "secret", transport=lambda p, q: {})
    assert list(a.active_deals(ComponentKind.GPU)) == []
