"""Best Buy Developer API adapter.

API reference: https://developer.bestbuy.com/ (US-only). Free tier is
ample for the MVP: 5 req/s, 50k/day. The adapter is transport-agnostic;
callers inject a ``Transport`` callable so unit tests can replay canned
responses without any network.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, Protocol

from pca.core.errors import MarketError, RateLimitedError
from pca.core.models import ComponentKind, Deal, MarketItem, StockStatus

Transport = Callable[[str, dict[str, Any]], dict[str, Any]]


class _ConfigLike(Protocol):
    api_key: str | None


class BestBuyAdapter:
    """BestBuy adapter. Uses category IDs to filter by ``ComponentKind``."""

    name = "bestbuy"

    _KIND_CATEGORY: dict[ComponentKind, str] = {
        ComponentKind.CPU: "abcat0507010",
        ComponentKind.GPU: "abcat0507002",
        ComponentKind.RAM: "abcat0507009",
        ComponentKind.STORAGE: "abcat0504001",
        ComponentKind.MOTHERBOARD: "abcat0507012",
        ComponentKind.PSU: "abcat0507005",
        ComponentKind.CASE: "abcat0507000",
        ComponentKind.COOLER: "abcat0507015",
    }

    def __init__(
        self,
        api_key: str | None,
        *,
        transport: Transport,
    ) -> None:
        self._api_key = api_key
        self._transport = transport

    def is_available(self) -> bool:
        return bool(self._api_key)

    # ------------------------------------------------------------------
    # Public MarketAdapter surface
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
        if category is None:
            return ()
        path = f"products((categoryPath.id={category})&(search={_escape(query)}))"
        params = {
            "format": "json",
            "show": "sku,name,manufacturer,salePrice,regularPrice,url,inStoreAvailability,onlineAvailability",
            "pageSize": str(min(100, limit)),
            "apiKey": self._api_key,
        }
        raw = self._call(path, params)
        items: list[MarketItem] = []
        for p in raw.get("products", [])[:limit]:
            items.append(self._to_item(p, kind))
        return items

    def fetch_by_sku(self, sku: str) -> MarketItem | None:
        if not self.is_available():
            return None
        path = f"products({sku})"
        params = {
            "format": "json",
            "show": "sku,name,manufacturer,salePrice,regularPrice,url,inStoreAvailability,onlineAvailability,categoryPath",
            "apiKey": self._api_key,
        }
        raw = self._call(path, params)
        if not raw:
            return None
        kind = self._infer_kind(raw.get("categoryPath", []))
        return self._to_item(raw, kind)

    def active_deals(
        self,
        kind: ComponentKind | None = None,
    ) -> Iterable[Deal]:
        if not self.is_available():
            return ()
        categories = (
            [self._KIND_CATEGORY[kind]] if kind else list(self._KIND_CATEGORY.values())
        )
        deals: list[Deal] = []
        for cat in categories:
            path = f"products((categoryPath.id={cat})&(onSale=true))"
            params = {
                "format": "json",
                "show": "sku,salePrice,regularPrice",
                "pageSize": "25",
                "apiKey": self._api_key,
            }
            raw = self._call(path, params)
            for p in raw.get("products", []):
                sale = _decimal(p.get("salePrice"))
                regular = _decimal(p.get("regularPrice"))
                if sale is None or regular is None or regular <= 0:
                    continue
                discount = float(
                    100 * (regular - sale) / regular if regular > sale else 0
                )
                if discount <= 0:
                    continue
                deals.append(
                    Deal(
                        market_item_sku=f"BB-{p['sku']}",
                        source=self.name,
                        discount_pct=round(discount, 2),
                        original_price_usd=regular,
                    )
                )
        return deals

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _call(self, path: str, params: dict[str, Any]) -> dict[str, Any]:
        try:
            return self._transport(path, params)
        except RateLimitedError:
            raise
        except Exception as exc:  # noqa: BLE001 - adapter boundary
            raise MarketError(f"bestbuy call failed: {exc}") from exc

    def _to_item(self, p: dict[str, Any], kind: ComponentKind) -> MarketItem:
        price = _decimal(p.get("salePrice")) or _decimal(p.get("regularPrice")) or Decimal("0")
        stock = _stock(p)
        return MarketItem(
            sku=f"BB-{p.get('sku', 'UNKNOWN')}",
            kind=kind,
            vendor=str(p.get("manufacturer") or "Unknown"),
            model=str(p.get("name") or "Unknown"),
            price_usd=price,
            source=self.name,
            url=str(p.get("url") or "https://www.bestbuy.com/"),
            stock=stock,
            fetched_at=datetime.now(UTC),
            specs={},
        )

    @staticmethod
    def _infer_kind(category_path: list[dict[str, Any]]) -> ComponentKind:
        ids = {str(c.get("id", "")) for c in category_path}
        for kind, cat in BestBuyAdapter._KIND_CATEGORY.items():
            if cat in ids:
                return kind
        return ComponentKind.PERIPHERAL


def _escape(q: str) -> str:
    return q.replace("&", "").replace("(", "").replace(")", "").strip()


def _decimal(v: Any) -> Decimal | None:
    if v is None:
        return None
    try:
        d = Decimal(str(v))
    except (ValueError, ArithmeticError):
        return None
    return d if d >= 0 else Decimal("0")


def _stock(p: dict[str, Any]) -> StockStatus:
    online = bool(p.get("onlineAvailability"))
    instore = bool(p.get("inStoreAvailability"))
    if online or instore:
        return StockStatus.IN_STOCK
    if online is False and instore is False:
        return StockStatus.OUT_OF_STOCK
    return StockStatus.UNKNOWN
