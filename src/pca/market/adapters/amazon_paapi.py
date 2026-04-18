"""Amazon Product Advertising API 5 adapter.

The MVP exposes the same ``MarketAdapter`` surface as :class:`BestBuyAdapter`
but stays inert unless the user supplies an Associates access key, secret,
and tag. The actual SigV4 signing is deferred to when someone has credentials
to test against; until then the adapter relies on an injected transport so
tests can replay canned responses.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from pca.core.errors import MarketError
from pca.core.models import ComponentKind, Deal, MarketItem, StockStatus

Transport = Callable[[str, dict[str, Any]], dict[str, Any]]


class AmazonPaapiAdapter:
    name = "amazon-paapi"

    _KIND_SEARCH_INDEX: dict[ComponentKind, str] = {
        ComponentKind.CPU: "Computers",
        ComponentKind.GPU: "Computers",
        ComponentKind.RAM: "Computers",
        ComponentKind.STORAGE: "Computers",
        ComponentKind.MOTHERBOARD: "Computers",
        ComponentKind.PSU: "Computers",
        ComponentKind.CASE: "Computers",
        ComponentKind.COOLER: "Computers",
    }

    def __init__(
        self,
        access_key: str | None,
        secret_key: str | None,
        assoc_tag: str | None,
        *,
        transport: Transport,
        region: str = "us-east-1",
    ) -> None:
        self._access_key = access_key
        self._secret_key = secret_key
        self._assoc_tag = assoc_tag
        self._region = region
        self._transport = transport

    def is_available(self) -> bool:
        return bool(self._access_key and self._secret_key and self._assoc_tag)

    def search(
        self,
        kind: ComponentKind,
        query: str,
        *,
        limit: int = 10,
    ) -> Iterable[MarketItem]:
        if not self.is_available():
            return ()
        payload = {
            "Operation": "SearchItems",
            "SearchIndex": self._KIND_SEARCH_INDEX.get(kind, "Computers"),
            "Keywords": query,
            "ItemCount": min(10, limit),
            "Resources": [
                "Images.Primary.Small",
                "ItemInfo.Title",
                "ItemInfo.ByLineInfo",
                "Offers.Listings.Price",
                "Offers.Listings.Availability.Message",
            ],
            "PartnerTag": self._assoc_tag,
            "PartnerType": "Associates",
            "Marketplace": "www.amazon.com",
        }
        try:
            raw = self._transport("SearchItems", payload)
        except Exception as exc:  # noqa: BLE001 - adapter boundary
            raise MarketError(f"amazon paapi call failed: {exc}") from exc

        items: list[MarketItem] = []
        for it in raw.get("SearchResult", {}).get("Items", []):
            items.append(self._to_item(it, kind))
        return items

    def fetch_by_sku(self, sku: str) -> MarketItem | None:
        if not self.is_available():
            return None
        payload = {
            "Operation": "GetItems",
            "ItemIds": [sku],
            "Resources": [
                "ItemInfo.Title",
                "ItemInfo.ByLineInfo",
                "Offers.Listings.Price",
                "Offers.Listings.Availability.Message",
            ],
            "PartnerTag": self._assoc_tag,
            "PartnerType": "Associates",
            "Marketplace": "www.amazon.com",
        }
        raw = self._transport("GetItems", payload)
        items = raw.get("ItemsResult", {}).get("Items", [])
        if not items:
            return None
        return self._to_item(items[0], ComponentKind.PERIPHERAL)

    def active_deals(
        self,
        kind: ComponentKind | None = None,
    ) -> Iterable[Deal]:
        # PA-API does not expose discount feeds; Keepa is the intended source.
        del kind
        return ()

    def _to_item(self, it: dict[str, Any], kind: ComponentKind) -> MarketItem:
        asin = str(it.get("ASIN", "UNKNOWN"))
        info = it.get("ItemInfo", {})
        offers = it.get("Offers", {}).get("Listings") or [{}]
        listing = offers[0]

        title = info.get("Title", {}).get("DisplayValue", "Unknown")
        vendor = (
            info.get("ByLineInfo", {}).get("Manufacturer", {}).get("DisplayValue")
            or info.get("ByLineInfo", {}).get("Brand", {}).get("DisplayValue")
            or "Unknown"
        )
        price_block = listing.get("Price", {}) or {}
        amount = price_block.get("Amount")
        price = Decimal(str(amount)) if amount is not None else Decimal("0")

        return MarketItem(
            sku=f"AMZ-{asin}",
            kind=kind,
            vendor=str(vendor),
            model=str(title),
            price_usd=price,
            source=self.name,
            url=str(it.get("DetailPageURL") or "https://www.amazon.com/"),
            stock=StockStatus.UNKNOWN,
            fetched_at=datetime.now(UTC),
            specs={},
        )
