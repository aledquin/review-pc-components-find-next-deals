"""eBay Browse API adapter (US, USD).

Docs: https://developer.ebay.com/api-docs/buy/browse/overview.html

Authentication uses OAuth2 client-credentials. The adapter does not manage the
token refresh dance itself - callers hand in a ``Transport`` that is expected
to attach a valid Bearer token. Tests replay cassettes through a fake
transport, so we never touch the network from unit/functional tests.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from pca.core.errors import MarketError, RateLimitedError
from pca.core.models import ComponentKind, Deal, MarketItem, StockStatus

Transport = Callable[[str, dict[str, Any]], dict[str, Any]]


class EbayBrowseAdapter:
    """Read-only wrapper over /buy/browse/v1/item_summary/search."""

    name = "ebay"

    # Map our kinds to eBay category IDs (PC Components tree, EBAY_US).
    _KIND_CATEGORY: dict[ComponentKind, str] = {
        ComponentKind.CPU: "164",
        ComponentKind.GPU: "27386",
        ComponentKind.RAM: "170083",
        ComponentKind.STORAGE: "175669",
        ComponentKind.MOTHERBOARD: "1244",
        ComponentKind.PSU: "42017",
        ComponentKind.CASE: "42015",
        ComponentKind.COOLER: "131487",
    }

    def __init__(
        self,
        client_id: str | None,
        client_secret: str | None,
        *,
        transport: Transport,
        marketplace: str = "EBAY_US",
    ) -> None:
        self._client_id = client_id
        self._client_secret = client_secret
        self._transport = transport
        self._marketplace = marketplace

    def is_available(self) -> bool:
        return bool(self._client_id and self._client_secret)

    # ------------------------------------------------------------------
    # MarketAdapter surface
    # ------------------------------------------------------------------

    def search(
        self,
        kind: ComponentKind,
        query: str,
        *,
        limit: int = 20,
    ) -> Iterable[MarketItem]:
        if not self.is_available():
            return ()
        category = self._KIND_CATEGORY.get(kind)
        params: dict[str, Any] = {
            "q": query,
            "limit": str(min(200, limit)),
            "filter": "conditionIds:{1000|1500|2000|3000}",  # new + refurb tiers
        }
        if category:
            params["category_ids"] = category
        raw = self._call("/buy/browse/v1/item_summary/search", params)
        items: list[MarketItem] = []
        for s in raw.get("itemSummaries", [])[:limit]:
            item = self._to_item(s, kind)
            if item is not None:
                items.append(item)
        return items

    def fetch_by_sku(self, sku: str) -> MarketItem | None:
        if not self.is_available() or not sku:
            return None
        item_id = sku.removeprefix("EBAY-")
        raw = self._call(f"/buy/browse/v1/item/{item_id}", {})
        if not raw:
            return None
        kind = self._infer_kind(raw.get("categoryPath", ""))
        return self._to_item(raw, kind)

    def active_deals(
        self,
        kind: ComponentKind | None = None,
    ) -> Iterable[Deal]:
        if not self.is_available():
            return ()
        categories = (
            [self._KIND_CATEGORY[kind]]
            if kind and kind in self._KIND_CATEGORY
            else list(self._KIND_CATEGORY.values())
        )
        deals: list[Deal] = []
        for cat in categories:
            raw = self._call(
                "/buy/browse/v1/item_summary/search",
                {
                    "category_ids": cat,
                    "filter": "deliveryCountry:US,buyingOptions:{FIXED_PRICE}",
                    "sort": "price",
                    "limit": "50",
                },
            )
            for s in raw.get("itemSummaries", []):
                mp = _decimal((s.get("marketingPrice") or {}).get("originalPrice", {}).get("value"))
                price = _decimal((s.get("price") or {}).get("value"))
                if mp is None or price is None or mp <= 0 or mp <= price:
                    continue
                discount = float(100 * (mp - price) / mp)
                if discount <= 0:
                    continue
                deals.append(
                    Deal(
                        market_item_sku=f"EBAY-{s.get('itemId', 'UNKNOWN')}",
                        source=self.name,
                        discount_pct=round(discount, 2),
                        original_price_usd=mp,
                    )
                )
        return deals

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _call(self, path: str, params: dict[str, Any]) -> dict[str, Any]:
        params = dict(params)
        params.setdefault("X-EBAY-C-MARKETPLACE-ID", self._marketplace)
        try:
            return self._transport(path, params)
        except RateLimitedError:
            raise
        except Exception as exc:  # noqa: BLE001 - adapter boundary
            raise MarketError(f"ebay call failed: {exc}") from exc

    def _to_item(self, s: dict[str, Any], kind: ComponentKind) -> MarketItem | None:
        price = _decimal((s.get("price") or {}).get("value"))
        if price is None:
            return None
        shipping = _decimal(
            ((s.get("shippingOptions") or [{}])[0].get("shippingCost") or {}).get("value")
        )
        total = price + (shipping or Decimal("0"))
        stock = _stock(s)
        item_id = str(s.get("itemId") or s.get("legacyItemId") or "UNKNOWN")
        return MarketItem(
            sku=f"EBAY-{item_id}",
            kind=kind,
            vendor=str((s.get("seller") or {}).get("username") or "ebay-seller"),
            model=str(s.get("title") or "Unknown"),
            price_usd=total,
            source=self.name,
            url=str(s.get("itemWebUrl") or "https://www.ebay.com/"),
            stock=stock,
            fetched_at=datetime.now(UTC),
            specs={"condition": str(s.get("condition") or "")},
        )

    @staticmethod
    def _infer_kind(category_path: str) -> ComponentKind:
        path = category_path.lower()
        if "cpu" in path or "processor" in path:
            return ComponentKind.CPU
        if "graphics" in path or "video" in path:
            return ComponentKind.GPU
        if "memory" in path or "ram " in path:
            return ComponentKind.RAM
        if "storage" in path or "ssd" in path or "hard drive" in path:
            return ComponentKind.STORAGE
        if "motherboard" in path:
            return ComponentKind.MOTHERBOARD
        if "power supply" in path or "psu" in path:
            return ComponentKind.PSU
        return ComponentKind.PERIPHERAL


def _decimal(v: Any) -> Decimal | None:
    if v is None:
        return None
    try:
        d = Decimal(str(v))
    except (ValueError, ArithmeticError):
        return None
    return d if d >= 0 else Decimal("0")


def _stock(s: dict[str, Any]) -> StockStatus:
    if s.get("itemEndDate"):
        # listing has an end date; treat as IN_STOCK while active.
        return StockStatus.IN_STOCK
    qty = s.get("estimatedAvailabilities")
    if qty:
        first = qty[0] if isinstance(qty, list) else qty
        status = str((first or {}).get("availabilityThresholdType", "")).upper()
        if status in {"MORE_THAN", "AVAILABLE"}:
            return StockStatus.IN_STOCK
        if status == "LIMITED_STOCK":
            return StockStatus.LOW_STOCK
    return StockStatus.UNKNOWN
