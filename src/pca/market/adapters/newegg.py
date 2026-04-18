"""Newegg adapter - **disabled by default**.

Newegg does not expose a public product catalog API. Our only legal ingestion
path is an affiliate feed (Impact, CJ, or Newegg's own program) delivered as a
flat file (CSV/TSV) on a schedule. This adapter parses such a feed when its
local path is provided.

HTML scraping is explicitly disallowed by Newegg's ToS (see
``docs/data-sources-tos.md``). We keep the scraper surface intentionally
absent so that no accidental code path talks to ``newegg.com`` at runtime.
"""

from __future__ import annotations

import csv
from collections.abc import Iterable
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from pca.core.models import ComponentKind, Deal, MarketItem, StockStatus


class NeweggFeedAdapter:
    """Reads a locally cached affiliate feed. Never calls newegg.com."""

    name = "newegg"

    _KIND_KEYWORDS: dict[ComponentKind, tuple[str, ...]] = {
        ComponentKind.CPU: ("cpu", "processor"),
        ComponentKind.GPU: ("gpu", "graphics", "video card"),
        ComponentKind.RAM: ("ram", "memory"),
        ComponentKind.STORAGE: ("ssd", "hdd", "storage", "hard drive", "nvme"),
        ComponentKind.MOTHERBOARD: ("motherboard", "mainboard"),
        ComponentKind.PSU: ("power supply", "psu"),
        ComponentKind.CASE: ("case", "chassis"),
        ComponentKind.COOLER: ("cpu cooler", "fan", "aio"),
    }

    def __init__(self, feed_path: Path | None) -> None:
        self._path = feed_path

    def is_available(self) -> bool:
        return self._path is not None and self._path.exists()

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
        needle = query.lower().strip()
        out: list[MarketItem] = []
        for row in self._iter_rows():
            if kind is not None and self._infer_kind(row) != kind:
                continue
            if needle and needle not in (row.get("name", "") + row.get("brand", "")).lower():
                continue
            item = self._to_item(row)
            if item is not None:
                out.append(item)
            if len(out) >= limit:
                break
        return out

    def fetch_by_sku(self, sku: str) -> MarketItem | None:
        if not self.is_available():
            return None
        key = sku.removeprefix("NE-")
        for row in self._iter_rows():
            if str(row.get("sku", "")) == key:
                return self._to_item(row)
        return None

    def active_deals(
        self,
        kind: ComponentKind | None = None,
    ) -> Iterable[Deal]:
        if not self.is_available():
            return ()
        deals: list[Deal] = []
        for row in self._iter_rows():
            if kind is not None and self._infer_kind(row) != kind:
                continue
            price = _decimal(row.get("sale_price"))
            regular = _decimal(row.get("price"))
            if price is None or regular is None or regular <= price:
                continue
            discount = float(100 * (regular - price) / regular)
            if discount <= 0:
                continue
            deals.append(
                Deal(
                    market_item_sku=f"NE-{row.get('sku', 'UNKNOWN')}",
                    source=self.name,
                    discount_pct=round(discount, 2),
                    original_price_usd=regular,
                )
            )
        return deals

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _iter_rows(self) -> Iterable[dict[str, str]]:
        assert self._path is not None
        # CSV with a header row; delimiter sniffed.
        with self._path.open("r", encoding="utf-8", newline="") as fh:
            sample = fh.read(4096)
            fh.seek(0)
            try:
                dialect = csv.Sniffer().sniff(sample, delimiters=",;\t")
            except csv.Error:
                dialect = csv.excel
            reader = csv.DictReader(fh, dialect=dialect)
            for row in reader:
                yield {k.strip().lower(): (v or "").strip() for k, v in row.items() if k}

    def _infer_kind(self, row: dict[str, str]) -> ComponentKind:
        blob = " ".join([row.get("category", ""), row.get("subcategory", ""), row.get("name", "")]).lower()
        for k, keywords in self._KIND_KEYWORDS.items():
            if any(kw in blob for kw in keywords):
                return k
        return ComponentKind.PERIPHERAL

    def _to_item(self, row: dict[str, str]) -> MarketItem | None:
        price = _decimal(row.get("sale_price") or row.get("price"))
        if price is None:
            return None
        return MarketItem(
            sku=f"NE-{row.get('sku') or row.get('id') or 'UNKNOWN'}",
            kind=self._infer_kind(row),
            vendor=row.get("brand", "Unknown") or "Unknown",
            model=row.get("name", "Unknown") or "Unknown",
            price_usd=price,
            source=self.name,
            url=row.get("url", "https://www.newegg.com/") or "https://www.newegg.com/",
            stock=_stock(row),
            fetched_at=datetime.now(UTC),
            specs={},
        )


def _decimal(v: str | None) -> Decimal | None:
    if v is None or str(v).strip() == "":
        return None
    try:
        d = Decimal(str(v).replace("$", "").replace(",", ""))
    except (ValueError, ArithmeticError):
        return None
    return d if d >= 0 else Decimal("0")


def _stock(row: dict[str, str]) -> StockStatus:
    avail = row.get("availability", "").lower()
    if "in stock" in avail:
        return StockStatus.IN_STOCK
    if "out" in avail or "sold out" in avail:
        return StockStatus.OUT_OF_STOCK
    if "limited" in avail or "low" in avail:
        return StockStatus.LOW_STOCK
    return StockStatus.UNKNOWN
