"""Functional test for ``pca market-refresh``.

Uses a fake adapter registered at runtime via a monkeypatch on
``pca.market.adapter.get_registry`` so the command never touches the
network.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest
from typer.testing import CliRunner

from pca.core.models import ComponentKind, Deal, MarketItem, StockStatus
from pca.market.adapter import AdapterRegistry
from pca.ui.cli.app import app
from tests.fixtures import INV_DIR


class _FakeAdapter:
    name = "fake"

    def is_available(self) -> bool:
        return True

    def search(
        self, kind: ComponentKind, query: str, *, limit: int = 20
    ) -> Iterable[MarketItem]:
        yield MarketItem(
            sku=f"{kind.value}-1",
            kind=kind,
            vendor="Acme",
            model=f"Acme {kind.value}",
            price_usd=Decimal("199.99"),
            source="fake",
            url="https://example.test/x",
            stock=StockStatus.IN_STOCK,
            fetched_at=datetime.now(UTC),
        )

    def fetch_by_sku(self, sku: str) -> MarketItem | None:
        return None

    def active_deals(self, kind: ComponentKind | None = None) -> Iterable[Deal]:
        return []


@pytest.fixture
def _fake_registry(monkeypatch: pytest.MonkeyPatch) -> AdapterRegistry:
    reg = AdapterRegistry()
    reg.register(_FakeAdapter())
    monkeypatch.setattr("pca.market.adapter.get_registry", lambda: reg)
    monkeypatch.setattr("pca.ui.cli.app._build_registry", lambda settings: reg)
    return reg


def test_market_refresh_writes_snapshot(
    tmp_path: Path, _fake_registry: AdapterRegistry
) -> None:
    out = tmp_path / "fresh.json"
    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "market-refresh",
            "--stub",
            str(INV_DIR / "rig_mid.json"),
            "--out",
            str(out),
        ],
    )
    assert result.exit_code == 0, result.stdout
    assert out.is_file()
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["items"], "refreshed snapshot should contain items"
    assert "fake" in data["sources"]


def test_market_refresh_without_creds_fails_gracefully(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """End-to-end via the real factory - with no creds, exit is non-zero
    and the error message points at env vars (not a traceback)."""
    from pca.core.config import reset_settings_cache

    for var in (
        "PCA_BESTBUY_API_KEY",
        "PCA_EBAY_CLIENT_ID",
        "PCA_EBAY_CLIENT_SECRET",
        "PCA_AMAZON_ACCESS_KEY",
        "PCA_AMAZON_SECRET_KEY",
        "PCA_AMAZON_ASSOC_TAG",
        "PCA_NEWEGG_FEED_PATH",
        "PCA_ENABLE_ADAPTERS",
        "PCA_ALLOW_PLUGINS",
    ):
        monkeypatch.delenv(var, raising=False)
    reset_settings_cache()

    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "market-refresh",
            "--stub",
            str(INV_DIR / "rig_mid.json"),
            "--out",
            str(tmp_path / "fresh.json"),
        ],
    )
    assert result.exit_code != 0
    # Message should mention env vars to help the user fix it.
    combined = (result.stdout or "") + str(result.exception or "")
    assert "PCA_BESTBUY_API_KEY" in combined or "no adapters" in combined.lower()
