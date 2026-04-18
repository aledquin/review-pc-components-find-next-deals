"""Functional tests for the Newegg affiliate-feed adapter.

The adapter never reaches newegg.com; we drive it through a tmp_path CSV.
"""

from __future__ import annotations

import csv
from decimal import Decimal
from pathlib import Path

import pytest

from pca.core.models import ComponentKind
from pca.market.adapters.newegg import NeweggFeedAdapter


@pytest.fixture
def feed(tmp_path: Path) -> Path:
    path = tmp_path / "newegg-feed.csv"
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(
            fh,
            fieldnames=[
                "sku",
                "brand",
                "name",
                "category",
                "subcategory",
                "price",
                "sale_price",
                "availability",
                "url",
            ],
        )
        writer.writeheader()
        writer.writerow(
            {
                "sku": "N82E16819113745",
                "brand": "AMD",
                "name": "Ryzen 7 7800X3D 8-Core CPU",
                "category": "Components",
                "subcategory": "CPU / Processors",
                "price": "449.00",
                "sale_price": "399.00",
                "availability": "In stock",
                "url": "https://www.newegg.com/p/N82E16819113745",
            }
        )
        writer.writerow(
            {
                "sku": "N82E16820236993",
                "brand": "G.Skill",
                "name": "Trident Z5 2x16GB DDR5-6000 Memory",
                "category": "Components",
                "subcategory": "Memory",
                "price": "129.99",
                "sale_price": "",
                "availability": "Out of stock",
                "url": "https://www.newegg.com/p/N82E16820236993",
            }
        )
    return path


def test_missing_feed_is_unavailable(tmp_path: Path) -> None:
    adapter = NeweggFeedAdapter(tmp_path / "nope.csv")
    assert adapter.is_available() is False
    assert list(adapter.search(ComponentKind.CPU, "ryzen")) == []


def test_search_filters_by_kind(feed: Path) -> None:
    adapter = NeweggFeedAdapter(feed)
    cpus = list(adapter.search(ComponentKind.CPU, "ryzen"))
    assert len(cpus) == 1
    assert cpus[0].sku == "NE-N82E16819113745"
    assert cpus[0].price_usd == Decimal("399.00")
    assert cpus[0].vendor == "AMD"


def test_active_deals_only_for_discounted(feed: Path) -> None:
    adapter = NeweggFeedAdapter(feed)
    deals = list(adapter.active_deals())
    assert len(deals) == 1
    assert deals[0].market_item_sku == "NE-N82E16819113745"
    assert deals[0].discount_pct > 0


def test_fetch_by_sku_roundtrip(feed: Path) -> None:
    adapter = NeweggFeedAdapter(feed)
    item = adapter.fetch_by_sku("NE-N82E16820236993")
    assert item is not None
    assert item.kind == ComponentKind.RAM
    assert item.price_usd == Decimal("129.99")
