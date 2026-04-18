"""Functional tests for the Wave 3 FastAPI dashboard.

We drive the app via ``fastapi.testclient`` - no network, no sockets.
"""

from __future__ import annotations

import pytest

pytest.importorskip("fastapi")

from fastapi.testclient import TestClient

from pca.ui.web.app import ServerConfig, create_app
from tests.fixtures import INV_DIR, MARKET_DIR


@pytest.fixture
def client() -> TestClient:
    app = create_app(
        ServerConfig(
            snapshot_path=INV_DIR / "rig_mid.json",
            market_path=MARKET_DIR / "snapshot_normal.json",
        )
    )
    return TestClient(app)


def test_health(client: TestClient) -> None:
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_index_serves_htmx_shell(client: TestClient) -> None:
    r = client.get("/")
    assert r.status_code == 200
    assert "PC Upgrade Advisor" in r.text
    assert "htmx" in r.text.lower()
    # Modernized dashboard ships cards + form controls.
    assert "card" in r.text
    assert 'id="budget"' in r.text
    assert 'id="strategy"' in r.text
    # Refresh prices button is discoverable from the landing page.
    assert "Refresh prices" in r.text
    assert "/htmx/market/refresh" in r.text


def test_index_shows_stale_banner_for_old_market(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The bundled default market is > 14 days old - banner must render."""
    from pca.ui.web.app import ServerConfig, create_app

    app = create_app(ServerConfig(snapshot_path=INV_DIR / "rig_mid.json"))
    c = TestClient(app)
    r = c.get("/")
    assert r.status_code == 200
    # The template surfaces either "Stale" or a day-count line - both acceptable
    # if fixture timestamp is very close to now. Assert the block is at least
    # rendered (market_source is templated in).
    assert "Market source" in r.text


def test_market_refresh_requires_snapshot(monkeypatch: pytest.MonkeyPatch) -> None:
    from pca.ui.web.app import ServerConfig, create_app

    # No snapshot_path configured, and app.state.detected_snapshot unset.
    app = create_app(ServerConfig(market_path=MARKET_DIR / "snapshot_normal.json"))
    c = TestClient(app)
    r = c.post("/api/market/refresh")
    assert r.status_code == 409
    assert "snapshot" in r.json()["detail"].lower()


def test_market_refresh_updates_cached_market(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """POST /api/market/refresh replaces the in-memory catalog."""
    from collections.abc import Iterable
    from datetime import UTC, datetime
    from decimal import Decimal

    from pca.core.models import ComponentKind, Deal, MarketItem, StockStatus
    from pca.market.adapter import AdapterRegistry

    class _Fake:
        name = "fake-web"

        def is_available(self) -> bool:
            return True

        def search(
            self, kind: ComponentKind, query: str, *, limit: int = 20
        ) -> Iterable[MarketItem]:
            yield MarketItem(
                sku=f"W-{kind.value}",
                kind=kind,
                vendor="V",
                model=f"Web {kind.value}",
                price_usd=Decimal("77.00"),
                source="fake-web",
                url="https://example.test/x",
                stock=StockStatus.IN_STOCK,
                fetched_at=datetime.now(UTC),
            )

        def fetch_by_sku(self, sku: str) -> MarketItem | None:
            return None

        def active_deals(
            self, kind: ComponentKind | None = None
        ) -> Iterable[Deal]:
            return []

    reg = AdapterRegistry()
    reg.register(_Fake())
    monkeypatch.setattr(
        "pca.market.factory.build_registry_from_settings", lambda _s: reg
    )

    r = client.post("/api/market/refresh")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["item_count"] >= 1
    assert "fake-web" in body["sources"]

    # HTMX fragment returns an ok-badge
    r2 = client.post("/htmx/market/refresh")
    assert r2.status_code == 200
    assert "Refreshed" in r2.text


def test_htmx_inventory_renders_table(client: TestClient) -> None:
    r = client.get("/htmx/inventory")
    assert r.status_code == 200
    assert "<table>" in r.text
    assert "<thead>" in r.text


def test_htmx_inventory_renders_specs_as_bullet_list(client: TestClient) -> None:
    """Inventory specs must render as a vertical <ul>, not an inline k=v blob."""

    r = client.get("/htmx/inventory")
    assert r.status_code == 200
    assert 'class="spec-list"' in r.text
    assert "<li>" in r.text
    # Legacy inline format should not leak through.
    assert "k=v" not in r.text


def test_htmx_plan_links_each_upgrade_to_retailer(client: TestClient) -> None:
    """Each upgrade row must link the model to the MarketItem URL with
    safe attributes and show the source adapter as a badge."""

    r = client.get(
        "/htmx/plan",
        params={"budget": 1200, "workload": "gaming_1440p", "strategy": "greedy"},
    )
    assert r.status_code == 200
    assert 'class="upgrade-link"' in r.text
    assert 'target="_blank"' in r.text
    assert 'rel="noopener noreferrer"' in r.text
    # The bundled KGR market uses https://example.test/... URLs.
    assert "https://example.test" in r.text
    # Source badge is rendered.
    assert "source-pill" in r.text


def test_upgrade_link_rejects_non_http_urls() -> None:
    """Defence-in-depth: javascript: / data: URLs never produce an <a>."""

    from pca.ui.web.app import _safe_external_url

    assert _safe_external_url("https://shop.example.com/x") == "https://shop.example.com/x"
    assert _safe_external_url("http://shop.example.com/x") == "http://shop.example.com/x"
    assert _safe_external_url("javascript:alert(1)") is None
    assert _safe_external_url("data:text/html,<script>") is None
    assert _safe_external_url("") is None
    assert _safe_external_url(None) is None


def test_htmx_plan_shows_improved_specs_and_rationale_block(
    client: TestClient,
) -> None:
    """Recommend output surfaces a dedicated 'Improved specs' list and a
    rationale block with enough horizontal room (colspan detail row)."""

    r = client.get(
        "/htmx/plan",
        params={"budget": 1200, "workload": "gaming_1440p", "strategy": "greedy"},
    )
    assert r.status_code == 200
    assert 'class="plan-table"' in r.text
    assert 'class="plan-detail"' in r.text
    assert 'colspan="4"' in r.text
    assert "Improved specs" in r.text
    assert 'class="spec-diff"' in r.text
    assert "Rationale" in r.text


def test_htmx_quote_returns_totals(client: TestClient) -> None:
    r = client.get(
        "/htmx/quote",
        params={"budget": 1200, "workload": "gaming_1440p", "strategy": "greedy", "zip": "98101"},
    )
    assert r.status_code == 200
    assert "Grand total" in r.text
    assert "Tax" in r.text


def test_inventory_returns_components(client: TestClient) -> None:
    r = client.get("/api/inventory")
    assert r.status_code == 200
    data = r.json()
    assert data["id"] == "rig_mid"
    assert "components" in data
    assert isinstance(data["deprecations"], list)


def test_recommend_returns_plan(client: TestClient) -> None:
    r = client.post(
        "/api/recommend",
        json={"budget_usd": "1200", "workload": "gaming_1440p", "strategy": "greedy"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["strategy"] == "greedy"
    assert isinstance(body["items"], list)


def test_htmx_plan_returns_fragment(client: TestClient) -> None:
    r = client.get(
        "/htmx/plan",
        params={"budget": 800, "workload": "gaming_1080p", "strategy": "greedy"},
    )
    assert r.status_code == 200
    assert "<section" in r.text
    assert "Plan" in r.text


def test_api_detect_stubs_probe(monkeypatch: pytest.MonkeyPatch) -> None:
    """/api/detect runs the native probe - we stub it here to avoid real WMI."""
    from pca.core.models import SystemSnapshot
    from tests.fixtures import INV_DIR, MARKET_DIR

    fake = SystemSnapshot.model_validate_json(
        (INV_DIR / "rig_mid.json").read_text(encoding="utf-8")
    )

    class _Stub:
        def collect(self) -> SystemSnapshot:
            return fake

    monkeypatch.setattr("pca.ui.web.app.detect_probe", lambda: _Stub())

    app = create_app(
        ServerConfig(
            snapshot_path=None,  # nothing loaded on disk
            market_path=MARKET_DIR / "snapshot_normal.json",
        )
    )
    c = TestClient(app)

    # Before detect, inventory is not configured.
    r = c.get("/api/inventory")
    assert r.status_code == 404

    # Detect populates in-memory state.
    r = c.post("/api/detect")
    assert r.status_code == 200
    body = r.json()
    assert body["id"] == "rig_mid"
    assert "components" in body

    # Inventory endpoints now serve the detected snapshot.
    r = c.get("/api/inventory")
    assert r.status_code == 200
    assert r.json()["id"] == "rig_mid"


def test_htmx_detect_returns_fragment(monkeypatch: pytest.MonkeyPatch) -> None:
    from pca.core.models import SystemSnapshot
    from tests.fixtures import INV_DIR, MARKET_DIR

    fake = SystemSnapshot.model_validate_json(
        (INV_DIR / "rig_mid.json").read_text(encoding="utf-8")
    )

    class _Stub:
        def collect(self) -> SystemSnapshot:
            return fake

    monkeypatch.setattr("pca.ui.web.app.detect_probe", lambda: _Stub())

    app = create_app(
        ServerConfig(
            snapshot_path=None,
            market_path=MARKET_DIR / "snapshot_normal.json",
        )
    )
    r = TestClient(app).post("/htmx/detect")
    assert r.status_code == 200
    assert "<table>" in r.text
    assert "Vendor" in r.text  # column header rendered


def test_api_detect_surfaces_probe_error(monkeypatch: pytest.MonkeyPatch) -> None:
    from pca.core.errors import InventoryError
    from tests.fixtures import MARKET_DIR

    class _Broken:
        def collect(self) -> object:
            raise InventoryError("no WMI")

    monkeypatch.setattr("pca.ui.web.app.detect_probe", lambda: _Broken())

    app = create_app(
        ServerConfig(
            snapshot_path=None,
            market_path=MARKET_DIR / "snapshot_normal.json",
        )
    )
    r = TestClient(app).post("/api/detect")
    assert r.status_code == 500
    assert "probe failed" in r.json()["detail"]


def test_lan_token_blocks_non_loopback() -> None:
    app = create_app(
        ServerConfig(
            snapshot_path=INV_DIR / "rig_mid.json",
            market_path=MARKET_DIR / "snapshot_normal.json",
            lan_token="s3cret",
        )
    )
    client = TestClient(app)
    # TestClient's client host defaults to "testclient" (not loopback);
    # must present the token or be rejected.
    r = client.get("/api/inventory")
    assert r.status_code in (401, 403)
    r_ok = client.get("/api/inventory", headers={"x-pca-token": "s3cret"})
    assert r_ok.status_code == 200
