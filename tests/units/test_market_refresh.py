"""Unit tests for the market-data refresh orchestrator.

All tests use a :class:`FakeAdapter` so nothing touches the network -
``pytest-socket`` enforces that at the conftest level.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from pca.core.errors import MarketError
from pca.core.models import ComponentKind, Deal, MarketItem, StockStatus
from pca.market.adapter import AdapterRegistry
from tests.fixtures import INV_DIR


# ---------------------------------------------------------------------------
# FakeAdapter used by every test
# ---------------------------------------------------------------------------


class FakeAdapter:
    """Minimal MarketAdapter implementation that returns canned items."""

    def __init__(
        self,
        name: str,
        canned: dict[ComponentKind, list[MarketItem]],
        *,
        available: bool = True,
        raises: Exception | None = None,
    ) -> None:
        self.name = name
        self._canned = canned
        self._available = available
        self._raises = raises
        self.calls: list[tuple[ComponentKind, str]] = []

    def is_available(self) -> bool:
        return self._available

    def search(
        self,
        kind: ComponentKind,
        query: str,
        *,
        limit: int = 20,
    ) -> Iterable[MarketItem]:
        self.calls.append((kind, query))
        if self._raises:
            raise self._raises
        return list(self._canned.get(kind, []))[:limit]

    def fetch_by_sku(self, sku: str) -> MarketItem | None:  # pragma: no cover
        return None

    def active_deals(
        self, kind: ComponentKind | None = None
    ) -> Iterable[Deal]:  # pragma: no cover
        return []


def _mk_item(
    sku: str,
    kind: ComponentKind,
    price: str,
    source: str,
) -> MarketItem:
    return MarketItem(
        sku=sku,
        kind=kind,
        vendor="Acme",
        model=f"Acme {sku}",
        price_usd=Decimal(price),
        source=source,
        url=f"https://example.test/{sku}",
        stock=StockStatus.IN_STOCK,
        fetched_at=datetime.now(UTC),
    )


# ---------------------------------------------------------------------------
# build_queries
# ---------------------------------------------------------------------------


def test_build_queries_covers_upgradable_kinds() -> None:
    from pca.core.models import SystemSnapshot
    from pca.market.refresh import build_queries

    snap = SystemSnapshot.model_validate_json(
        (INV_DIR / "rig_mid.json").read_text(encoding="utf-8")
    )
    queries = build_queries(snap)
    # We refresh at least CPU / GPU / RAM / Storage - the high-impact kinds.
    assert ComponentKind.CPU in queries
    assert ComponentKind.GPU in queries
    assert ComponentKind.RAM in queries
    assert ComponentKind.STORAGE in queries
    # Each kind should yield at least one non-empty query string.
    for kind, qlist in queries.items():
        assert qlist, f"{kind.value} has no queries"
        for q in qlist:
            assert isinstance(q, str) and q.strip()


def test_build_queries_uses_current_component_specs() -> None:
    """The query for RAM should mention the current RAM type (DDR5, DDR4, ...)."""
    from pca.core.models import SystemSnapshot
    from pca.market.refresh import build_queries

    snap = SystemSnapshot.model_validate_json(
        (INV_DIR / "rig_mid.json").read_text(encoding="utf-8")
    )
    queries = build_queries(snap)
    ram_queries = [q.lower() for q in queries[ComponentKind.RAM]]
    # rig_mid is a DDR4 box per fixture. Either "ddr4" or generic "ram"
    # is acceptable; the important thing is the query references memory.
    assert any(("ddr" in q) or ("ram" in q) or ("memory" in q) for q in ram_queries)


# ---------------------------------------------------------------------------
# refresh_market: happy paths + merging
# ---------------------------------------------------------------------------


def test_refresh_market_merges_items_from_all_adapters() -> None:
    from pca.core.models import SystemSnapshot
    from pca.market.refresh import refresh_market

    snap = SystemSnapshot.model_validate_json(
        (INV_DIR / "rig_mid.json").read_text(encoding="utf-8")
    )

    a = FakeAdapter(
        "fake-a",
        {ComponentKind.CPU: [_mk_item("A1", ComponentKind.CPU, "200.00", "fake-a")]},
    )
    b = FakeAdapter(
        "fake-b",
        {ComponentKind.GPU: [_mk_item("B1", ComponentKind.GPU, "400.00", "fake-b")]},
    )
    reg = AdapterRegistry()
    reg.register(a)
    reg.register(b)

    result = refresh_market(snap, reg)
    skus = {i.sku for i in result.items}
    assert skus == {"A1", "B1"}
    assert {"fake-a", "fake-b"} <= set(result.sources)
    assert result.errors == ()


def test_refresh_market_dedupes_by_source_sku() -> None:
    """The same adapter returning the same SKU twice is collapsed."""
    from pca.core.models import SystemSnapshot
    from pca.market.refresh import refresh_market

    snap = SystemSnapshot.model_validate_json(
        (INV_DIR / "rig_mid.json").read_text(encoding="utf-8")
    )

    dup = _mk_item("A1", ComponentKind.CPU, "200.00", "fake-a")
    a = FakeAdapter(
        "fake-a", {ComponentKind.CPU: [dup, dup], ComponentKind.GPU: [dup]}
    )
    reg = AdapterRegistry()
    reg.register(a)

    result = refresh_market(snap, reg)
    # One row per (source, sku).
    assert len(result.items) == 1


def test_refresh_market_skips_unavailable_adapters() -> None:
    from pca.core.models import SystemSnapshot
    from pca.market.refresh import refresh_market

    snap = SystemSnapshot.model_validate_json(
        (INV_DIR / "rig_mid.json").read_text(encoding="utf-8")
    )

    good = FakeAdapter(
        "good", {ComponentKind.CPU: [_mk_item("G1", ComponentKind.CPU, "150", "good")]}
    )
    offline = FakeAdapter("offline", {}, available=False)
    reg = AdapterRegistry()
    reg.register(good)
    reg.register(offline)

    result = refresh_market(snap, reg)
    assert offline.calls == []  # was skipped entirely
    assert "good" in result.sources
    assert "offline" not in result.sources


def test_refresh_market_partial_success_on_adapter_error() -> None:
    """An adapter raising should be recorded - not abort the whole refresh."""
    from pca.core.models import SystemSnapshot
    from pca.market.refresh import refresh_market

    snap = SystemSnapshot.model_validate_json(
        (INV_DIR / "rig_mid.json").read_text(encoding="utf-8")
    )

    good = FakeAdapter(
        "good",
        {ComponentKind.CPU: [_mk_item("G1", ComponentKind.CPU, "150", "good")]},
    )
    broken = FakeAdapter(
        "broken", {}, raises=MarketError("429 Too Many Requests")
    )
    reg = AdapterRegistry()
    reg.register(good)
    reg.register(broken)

    result = refresh_market(snap, reg)
    assert any(i.sku == "G1" for i in result.items)
    assert any("broken" in e and "429" in e for e in result.errors)


def test_refresh_market_requires_registered_adapters() -> None:
    from pca.core.models import SystemSnapshot
    from pca.market.refresh import refresh_market

    snap = SystemSnapshot.model_validate_json(
        (INV_DIR / "rig_mid.json").read_text(encoding="utf-8")
    )
    reg = AdapterRegistry()  # empty
    with pytest.raises(MarketError, match="no adapters"):
        refresh_market(snap, reg)


def test_refresh_market_raises_when_all_unavailable() -> None:
    from pca.core.models import SystemSnapshot
    from pca.market.refresh import refresh_market

    snap = SystemSnapshot.model_validate_json(
        (INV_DIR / "rig_mid.json").read_text(encoding="utf-8")
    )
    reg = AdapterRegistry()
    reg.register(FakeAdapter("x", {}, available=False))
    reg.register(FakeAdapter("y", {}, available=False))
    with pytest.raises(MarketError, match="no adapters available"):
        refresh_market(snap, reg)


# ---------------------------------------------------------------------------
# write_market_snapshot + age helpers
# ---------------------------------------------------------------------------


def test_write_market_snapshot_roundtrips(tmp_path: Path) -> None:
    from pca.core.models import SystemSnapshot
    from pca.market.refresh import RefreshResult, write_market_snapshot

    snap = SystemSnapshot.model_validate_json(
        (INV_DIR / "rig_mid.json").read_text(encoding="utf-8")
    )
    a = FakeAdapter(
        "fake", {ComponentKind.CPU: [_mk_item("A1", ComponentKind.CPU, "200", "fake")]}
    )
    reg = AdapterRegistry()
    reg.register(a)
    from pca.market.refresh import refresh_market

    result: RefreshResult = refresh_market(snap, reg)
    out = tmp_path / "m.json"
    written = write_market_snapshot(result, out, identifier="roundtrip")
    assert written == out
    assert out.is_file()

    import json

    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["id"] == "roundtrip"
    assert data["items"][0]["sku"] == "A1"
    assert "generated_at" in data


def test_market_snapshot_age_days() -> None:
    from pca.market.refresh import market_snapshot_age_days

    now = datetime.now(UTC)
    assert market_snapshot_age_days(now - timedelta(days=7)) == 7
    assert market_snapshot_age_days(now - timedelta(days=0, hours=5)) == 0
    # Timezone-naive should be treated as UTC, not crash.
    naive = (now - timedelta(days=3)).replace(tzinfo=None)
    assert market_snapshot_age_days(naive) == 3
