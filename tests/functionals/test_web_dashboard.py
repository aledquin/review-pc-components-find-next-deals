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
