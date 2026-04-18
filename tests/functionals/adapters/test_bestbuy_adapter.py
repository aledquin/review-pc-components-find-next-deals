"""Contract tests for the Best Buy adapter.

Transport is stubbed with a canned response dict so these tests are
deterministic and do not need a live API key.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from pca.core.models import ComponentKind, StockStatus
from pca.market.adapters.bestbuy import BestBuyAdapter

CANNED_PRODUCTS = {
    "products": [
        {
            "sku": "5700X3D",
            "name": "AMD Ryzen 7 5700X3D",
            "manufacturer": "AMD",
            "salePrice": 199.99,
            "regularPrice": 239.99,
            "url": "https://bestbuy.com/site/5700x3d",
            "onlineAvailability": True,
            "inStoreAvailability": True,
        },
        {
            "sku": "5600",
            "name": "AMD Ryzen 5 5600",
            "manufacturer": "AMD",
            "salePrice": 119.99,
            "regularPrice": 119.99,
            "url": "https://bestbuy.com/site/5600",
            "onlineAvailability": True,
            "inStoreAvailability": False,
        },
    ]
}

SINGLE_PRODUCT = {
    "sku": "5700X3D",
    "name": "AMD Ryzen 7 5700X3D",
    "manufacturer": "AMD",
    "salePrice": 199.99,
    "regularPrice": 239.99,
    "url": "https://bestbuy.com/site/5700x3d",
    "onlineAvailability": True,
    "inStoreAvailability": True,
    "categoryPath": [{"id": "abcat0507010"}],
}


def fake_transport(path, params):
    if path.startswith("products("):
        if "(sku)" in path or path.startswith("products(5700X3D"):
            return SINGLE_PRODUCT
        return CANNED_PRODUCTS
    return {}


class TestBestBuyContract:
    def test_is_available_requires_api_key(self):
        assert BestBuyAdapter(None, transport=fake_transport).is_available() is False
        assert BestBuyAdapter("key", transport=fake_transport).is_available() is True

    def test_search_returns_market_items(self):
        adapter = BestBuyAdapter("key", transport=fake_transport)
        items = list(adapter.search(ComponentKind.CPU, "ryzen"))
        assert len(items) == 2
        it = items[0]
        assert it.sku == "BB-5700X3D"
        assert it.source == "bestbuy"
        assert it.kind is ComponentKind.CPU
        assert it.price_usd == Decimal("199.99")
        assert it.stock is StockStatus.IN_STOCK
        assert "5700X3D" in it.model

    def test_search_prefers_sale_price(self):
        adapter = BestBuyAdapter("key", transport=fake_transport)
        items = list(adapter.search(ComponentKind.CPU, "ryzen"))
        assert items[0].price_usd == Decimal("199.99")

    def test_search_respects_unsupported_kind(self):
        adapter = BestBuyAdapter("key", transport=fake_transport)
        assert list(adapter.search(ComponentKind.OS, "windows")) == []

    def test_fetch_by_sku(self):
        adapter = BestBuyAdapter("key", transport=fake_transport)
        it = adapter.fetch_by_sku("5700X3D")
        assert it is not None
        assert it.kind is ComponentKind.CPU
        assert it.sku == "BB-5700X3D"

    def test_active_deals_derives_discount_pct(self):
        adapter = BestBuyAdapter("key", transport=fake_transport)
        deals = list(adapter.active_deals(ComponentKind.CPU))
        assert len(deals) == 1
        d = deals[0]
        assert d.market_item_sku == "BB-5700X3D"
        assert 16.5 < d.discount_pct < 17.0

    @pytest.mark.parametrize("price", [-1, None, "not-a-number"])
    def test_search_is_robust_to_bad_price(self, price):
        adapter = BestBuyAdapter(
            "key",
            transport=lambda p, q: {"products": [{"sku": "X", "salePrice": price}]},
        )
        items = list(adapter.search(ComponentKind.CPU, "x"))
        assert len(items) == 1
        assert items[0].price_usd >= Decimal("0")
