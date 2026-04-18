"""eBay sold-listings adapter for used-market price discovery.

eBay exposes a Marketplace Insights API that returns *completed* (sold)
listings in the last 90 days. Access is restricted to approved partners; we
still ship this adapter so the rest of the codebase can consume used-market
``MarketItem``s without any plumbing changes.

When the approved partner token is absent the adapter reports itself as
unavailable and returns nothing - matching the "fail safe" posture of the
eBay Browse adapter.

This adapter intentionally marks every result with ``source='ebay-sold'`` so
downstream consumers (quote builder, UI) can filter used-market results
separately from new-market results. Perf scores are **not** attached; used
items rely on the catalog perf score assigned by kind/vendor/model.
"""

from __future__ import annotations

import statistics
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from pca.core.errors import MarketError, RateLimitedError
from pca.core.models import ComponentKind, Deal, MarketItem, StockStatus

Transport = Callable[[str, dict[str, Any]], dict[str, Any]]


@dataclass(frozen=True)
class SoldPriceStats:
    """Summary of sold-price distribution for a query."""

    median_usd: Decimal
    p25_usd: Decimal
    p75_usd: Decimal
    sample_size: int


class EbaySoldAdapter:
    """Read-only wrapper over /buy/marketplace_insights/v1_beta/item_sales/search."""

    name = "ebay-sold"

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
    # Public API (reuses the MarketAdapter surface where sensible)
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
        }
        if category:
            params["category_ids"] = category
        raw = self._call(
            "/buy/marketplace_insights/v1_beta/item_sales/search", params
        )
        items: list[MarketItem] = []
        for s in raw.get("itemSales", [])[:limit]:
            item = self._to_item(s, kind)
            if item is not None:
                items.append(item)
        return items

    def fetch_by_sku(self, sku: str) -> MarketItem | None:
        # Sold listings are historic; fetch-by-SKU doesn't apply.
        return None

    def active_deals(
        self,
        kind: ComponentKind | None = None,
    ) -> Iterable[Deal]:
        # Sold listings don't have "active" deals.
        return ()

    # ------------------------------------------------------------------
    # Used-market specific helpers
    # ------------------------------------------------------------------

    def sold_price_stats(
        self,
        kind: ComponentKind,
        query: str,
        *,
        limit: int = 200,
    ) -> SoldPriceStats | None:
        """Return median / P25 / P75 of sold prices, or None if sample too small."""
        items = list(self.search(kind, query, limit=limit))
        prices = [float(i.price_usd) for i in items if float(i.price_usd) > 0]
        if len(prices) < 5:
            return None
        prices.sort()
        q = statistics.quantiles(prices, n=4)  # [p25, p50, p75]
        return SoldPriceStats(
            median_usd=_to_decimal(q[1]),
            p25_usd=_to_decimal(q[0]),
            p75_usd=_to_decimal(q[2]),
            sample_size=len(prices),
        )

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
            raise MarketError(f"ebay-sold call failed: {exc}") from exc

    def _to_item(self, s: dict[str, Any], kind: ComponentKind) -> MarketItem | None:
        price = _to_decimal_maybe((s.get("lastSoldPrice") or {}).get("value"))
        if price is None:
            return None
        item_id = str(s.get("itemId") or s.get("legacyItemId") or "UNKNOWN")
        return MarketItem(
            sku=f"EBAYSOLD-{item_id}",
            kind=kind,
            vendor=str((s.get("seller") or {}).get("username") or "ebay-seller"),
            model=str(s.get("title") or "Unknown"),
            price_usd=price,
            source=self.name,
            url=str(s.get("itemWebUrl") or "https://www.ebay.com/"),
            stock=StockStatus.OUT_OF_STOCK,  # by definition - already sold
            fetched_at=datetime.now(UTC),
            specs={
                "condition": str(s.get("condition") or ""),
                "sold_at": str(s.get("lastSoldDate") or ""),
            },
        )


def _to_decimal(v: float) -> Decimal:
    return Decimal(str(round(v, 2)))


def _to_decimal_maybe(v: Any) -> Decimal | None:
    if v is None:
        return None
    try:
        d = Decimal(str(v))
    except (ValueError, ArithmeticError):
        return None
    return d if d >= 0 else Decimal("0")
