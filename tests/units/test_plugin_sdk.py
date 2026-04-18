"""Unit tests for the retailer plugin SDK."""

from __future__ import annotations

from typing import Any

import pytest

from pca.core.errors import MarketError
from pca.core.models import ComponentKind, Deal, MarketItem
from pca.market.adapter import AdapterRegistry
from pca.market.plugins import (
    ConformanceError,
    _ExamplePlugin,
    build_example_adapter,
    check_conformance,
    load_plugin_adapters,
)


class _Settings:
    pass


def test_example_plugin_is_conformant() -> None:
    adapter = build_example_adapter(_Settings())
    check_conformance(adapter)


def test_missing_method_raises_conformance_error() -> None:
    class Broken:
        name = "broken"

        def is_available(self) -> bool:
            return True

        def search(self, *_args, **_kwargs) -> list[MarketItem]:
            return []

        # fetch_by_sku intentionally missing.
        def active_deals(self, kind: Any = None) -> list[Deal]:
            return []

    with pytest.raises((MarketError, ConformanceError)):
        check_conformance(Broken())


def test_non_market_item_results_fail_conformance() -> None:
    class Liar(_ExamplePlugin):
        def search(self, *_args, **_kwargs):
            return [object()]

    with pytest.raises(ConformanceError):
        check_conformance(Liar())


def test_non_deal_results_fail_conformance() -> None:
    class Liar(_ExamplePlugin):
        def active_deals(self, *_args, **_kwargs):
            return [object()]

    with pytest.raises(ConformanceError):
        check_conformance(Liar())


def test_register_loaded_plugin_into_registry() -> None:
    adapter = build_example_adapter(_Settings())
    registry = AdapterRegistry()
    registry.register(adapter)
    assert registry.get("example-plugin") is adapter
    assert adapter in registry.available()


def test_load_plugin_adapters_accepts_missing_entry_points(monkeypatch) -> None:
    """When no plugins are installed, loader returns an empty tuple - not an error."""
    from pca.market import plugins

    class EmptyIterable:
        def __iter__(self):
            return iter(())

    monkeypatch.setattr(
        plugins.ilm,
        "entry_points",
        lambda group=None: EmptyIterable() if group else EmptyIterable(),
    )
    assert load_plugin_adapters(_Settings()) == ()


def test_load_plugin_invokes_factory(monkeypatch) -> None:
    from pca.market import plugins

    class FakeEP:
        name = "example"
        dist = None

        def load(self):
            return build_example_adapter

    monkeypatch.setattr(
        plugins.ilm,
        "entry_points",
        lambda group=None: [FakeEP()] if group == plugins.ENTRY_POINT_GROUP else [],
    )
    loaded = load_plugin_adapters(_Settings())
    assert len(loaded) == 1
    assert loaded[0].adapters[0].name == "example-plugin"


def test_example_plugin_search_returns_market_item() -> None:
    adapter = build_example_adapter(_Settings())
    items = list(adapter.search(ComponentKind.CPU, "test query"))
    assert len(items) == 1
    assert items[0].vendor == "Example"
    assert items[0].source == "example-plugin"
