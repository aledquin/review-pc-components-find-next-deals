"""Contract tests for the eBay Browse adapter. Transport is faked."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

import pytest

from pca.core.errors import MarketError
from pca.core.models import ComponentKind
from pca.market.adapters.ebay import EbayBrowseAdapter


def _canned_search() -> dict[str, Any]:
    return {
        "itemSummaries": [
            {
                "itemId": "v1|123456|0",
                "title": "AMD Ryzen 7 7800X3D",
                "price": {"value": "399.99", "currency": "USD"},
                "marketingPrice": {"originalPrice": {"value": "449.99", "currency": "USD"}},
                "shippingOptions": [
                    {"shippingCost": {"value": "0.00", "currency": "USD"}}
                ],
                "seller": {"username": "goodseller"},
                "itemWebUrl": "https://www.ebay.com/itm/123456",
                "condition": "New",
                "estimatedAvailabilities": [{"availabilityThresholdType": "MORE_THAN"}],
            },
            {
                "itemId": "v1|222222|0",
                "title": "Refurb RTX 4080",
                "price": {"value": "1100.00", "currency": "USD"},
                "seller": {"username": "refurb-shop"},
                "itemWebUrl": "https://www.ebay.com/itm/222222",
                "condition": "Seller refurbished",
            },
        ]
    }


def test_search_requires_credentials() -> None:
    adapter = EbayBrowseAdapter(None, None, transport=lambda p, q: {})
    assert adapter.is_available() is False
    assert list(adapter.search(ComponentKind.CPU, "ryzen")) == []


def test_search_emits_normalized_items() -> None:
    def fake(path: str, params: dict[str, Any]) -> dict[str, Any]:
        assert path.startswith("/buy/browse/v1/item_summary/search")
        return _canned_search()

    adapter = EbayBrowseAdapter("cid", "secret", transport=fake)
    items = list(adapter.search(ComponentKind.CPU, "ryzen", limit=5))
    assert len(items) == 2
    assert items[0].sku.startswith("EBAY-")
    assert items[0].price_usd == Decimal("399.99")
    assert items[0].source == "ebay"


def test_active_deals_flags_discount_only() -> None:
    def fake(path: str, params: dict[str, Any]) -> dict[str, Any]:
        return _canned_search()

    adapter = EbayBrowseAdapter("cid", "secret", transport=fake)
    deals = list(adapter.active_deals(ComponentKind.CPU))
    assert len(deals) == 1
    assert deals[0].discount_pct > 0
    assert deals[0].original_price_usd == Decimal("449.99")


def test_transport_errors_wrap_to_market_error() -> None:
    def boom(path: str, params: dict[str, Any]) -> dict[str, Any]:
        raise RuntimeError("timeout")

    adapter = EbayBrowseAdapter("cid", "secret", transport=boom)
    with pytest.raises(MarketError):
        list(adapter.search(ComponentKind.CPU, "ryzen"))
