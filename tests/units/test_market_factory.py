"""Tests for the adapter factory.

All tests run fully offline - the real httpx client is never constructed
because the tests cover either:

- shape of the built registry (no transport invocation), or
- transport construction via a ``transport_factory`` injection seam.

Network is banned by ``pytest-socket`` at the session level.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest

from pca.core.config import Settings
from pca.market.adapter import AdapterRegistry


def _settings(**kwargs: Any) -> Settings:
    """Build a Settings instance with overrides, bypassing env/.env."""
    defaults: dict[str, Any] = {
        # Explicitly disable every secret so tests don't leak real creds.
        "bestbuy_api_key": None,
        "ebay_client_id": None,
        "ebay_client_secret": None,
        "amazon_access_key": None,
        "amazon_secret_key": None,
        "amazon_assoc_tag": None,
        "newegg_feed_path": None,
        "enable_adapters": "",
        "allow_plugins": False,
    }
    defaults.update(kwargs)
    return Settings.model_construct(**defaults)


# ---------------------------------------------------------------------------
# Adapter inclusion logic
# ---------------------------------------------------------------------------


def test_factory_with_no_creds_returns_empty_registry() -> None:
    from pca.market.factory import build_registry_from_settings

    reg = build_registry_from_settings(_settings())
    assert isinstance(reg, AdapterRegistry)
    assert reg.all() == ()


def test_factory_auto_includes_adapter_when_creds_present() -> None:
    """With bestbuy_api_key set, the factory registers BestBuyAdapter
    even if enable_adapters is empty (auto-mode)."""
    from pca.market.factory import build_registry_from_settings

    reg = build_registry_from_settings(_settings(bestbuy_api_key="bb-key"))
    names = {a.name for a in reg.all()}
    assert "bestbuy" in names


def test_factory_allow_list_filters_adapters() -> None:
    """Setting enable_adapters explicitly restricts the registry."""
    from pca.market.factory import build_registry_from_settings

    reg = build_registry_from_settings(
        _settings(
            bestbuy_api_key="bb",
            ebay_client_id="id",
            ebay_client_secret="sec",
            enable_adapters="bestbuy",  # eBay excluded even though creds set
        )
    )
    names = {a.name for a in reg.all()}
    assert names == {"bestbuy"}


def test_factory_includes_ebay_when_both_creds_present() -> None:
    from pca.market.factory import build_registry_from_settings

    reg = build_registry_from_settings(
        _settings(ebay_client_id="id", ebay_client_secret="sec")
    )
    names = {a.name for a in reg.all()}
    assert "ebay" in names


def test_factory_skips_ebay_when_only_one_cred() -> None:
    from pca.market.factory import build_registry_from_settings

    reg = build_registry_from_settings(_settings(ebay_client_id="id"))
    names = {a.name for a in reg.all()}
    assert "ebay" not in names


def test_factory_includes_newegg_when_feed_path_exists(tmp_path: Any) -> None:
    from pca.market.factory import build_registry_from_settings

    feed = tmp_path / "feed.tsv"
    feed.write_text("", encoding="utf-8")
    reg = build_registry_from_settings(_settings(newegg_feed_path=feed))
    assert any(a.name == "newegg" for a in reg.all())


def test_factory_requested_but_uncredentialed_raises_clear_error() -> None:
    from pca.core.errors import MarketError
    from pca.market.factory import build_registry_from_settings

    with pytest.raises(MarketError, match="bestbuy"):
        build_registry_from_settings(
            _settings(enable_adapters="bestbuy")  # creds missing
        )


# ---------------------------------------------------------------------------
# Transport injection seam
# ---------------------------------------------------------------------------


def test_factory_uses_injected_transport_factory() -> None:
    """Tests can pass ``transport_factory`` so no httpx client is constructed."""
    from pca.market.factory import build_registry_from_settings

    calls: list[str] = []

    def fake_transport_factory(
        base_url: str, *, timeout_s: float, auth: Any | None = None
    ) -> Callable[[str, dict[str, Any]], dict[str, Any]]:
        calls.append(base_url)

        def _t(path: str, params: dict[str, Any]) -> dict[str, Any]:
            return {}

        return _t

    reg = build_registry_from_settings(
        _settings(bestbuy_api_key="bb"),
        transport_factory=fake_transport_factory,
    )
    assert any(a.name == "bestbuy" for a in reg.all())
    # Factory must have asked for at least one base URL.
    assert calls, "transport_factory was never called"


# ---------------------------------------------------------------------------
# Plugin loading
# ---------------------------------------------------------------------------


def test_factory_loads_plugins_when_allowed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """allow_plugins=True pulls entries from pca.market.plugins.load_plugin_adapters."""
    from pca.market.plugins import LoadedPlugin, _ExamplePlugin
    from pca.market.factory import build_registry_from_settings

    fake_plugin = LoadedPlugin(name="example", dist=None, adapters=(_ExamplePlugin(),))

    monkeypatch.setattr(
        "pca.market.factory.load_plugin_adapters",
        lambda settings: (fake_plugin,),
    )
    reg = build_registry_from_settings(_settings(allow_plugins=True))
    names = {a.name for a in reg.all()}
    assert "example-plugin" in names


def test_factory_ignores_plugins_when_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from pca.market.plugins import LoadedPlugin, _ExamplePlugin
    from pca.market.factory import build_registry_from_settings

    fake_plugin = LoadedPlugin(name="example", dist=None, adapters=(_ExamplePlugin(),))

    called = {"n": 0}

    def _loader(_settings: Any) -> Any:
        called["n"] += 1
        return (fake_plugin,)

    monkeypatch.setattr("pca.market.factory.load_plugin_adapters", _loader)
    build_registry_from_settings(_settings(allow_plugins=False))
    assert called["n"] == 0, "plugin loader must not run when allow_plugins=False"
