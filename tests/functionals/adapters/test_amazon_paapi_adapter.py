"""Contract tests for the Amazon PA-API adapter with canned transport."""

from __future__ import annotations

from decimal import Decimal

from pca.core.models import ComponentKind
from pca.market.adapters.amazon_paapi import AmazonPaapiAdapter

CANNED_SEARCH = {
    "SearchResult": {
        "Items": [
            {
                "ASIN": "B09XYZ",
                "DetailPageURL": "https://www.amazon.com/dp/B09XYZ",
                "ItemInfo": {
                    "Title": {"DisplayValue": "AMD Ryzen 7 7800X3D"},
                    "ByLineInfo": {"Manufacturer": {"DisplayValue": "AMD"}},
                },
                "Offers": {
                    "Listings": [
                        {
                            "Price": {"Amount": 389.99, "Currency": "USD"},
                            "Availability": {"Message": "In Stock"},
                        }
                    ]
                },
            }
        ]
    }
}


class TestAmazonPaapiContract:
    def test_is_available_requires_all_three_creds(self):
        t = lambda p, q: {}
        assert AmazonPaapiAdapter(None, None, None, transport=t).is_available() is False
        assert AmazonPaapiAdapter("a", None, None, transport=t).is_available() is False
        assert AmazonPaapiAdapter("a", "b", None, transport=t).is_available() is False
        assert AmazonPaapiAdapter("a", "b", "t", transport=t).is_available() is True

    def test_search_maps_canned_response(self):
        adapter = AmazonPaapiAdapter(
            "a", "b", "t", transport=lambda p, q: CANNED_SEARCH
        )
        items = list(adapter.search(ComponentKind.CPU, "ryzen 7800X3D"))
        assert len(items) == 1
        it = items[0]
        assert it.sku == "AMZ-B09XYZ"
        assert it.source == "amazon-paapi"
        assert it.price_usd == Decimal("389.99")
        assert "7800X3D" in it.model
        assert it.vendor == "AMD"

    def test_search_when_unavailable_returns_empty(self):
        adapter = AmazonPaapiAdapter(None, None, None, transport=lambda p, q: {})
        assert list(adapter.search(ComponentKind.CPU, "anything")) == []

    def test_active_deals_always_empty_for_paapi(self):
        adapter = AmazonPaapiAdapter(
            "a", "b", "t", transport=lambda p, q: CANNED_SEARCH
        )
        assert list(adapter.active_deals()) == []
