"""``MarketAdapter`` contract + adapter registry.

Every retailer integration implements this interface. Adapters:

- Are transport-agnostic (HTTPX client is injected).
- Normalize every result into a ``MarketItem``.
- Never call the network in unit tests (protected by ``pytest-socket``).
- Declare a stable ``name`` used as the ``source`` field on ``MarketItem``.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Protocol

from pca.core.errors import AdapterUnavailableError
from pca.core.models import ComponentKind, Deal, MarketItem


class MarketAdapter(Protocol):
    """Read-only view of a retailer."""

    @property
    def name(self) -> str: ...

    def is_available(self) -> bool: ...

    def search(
        self,
        kind: ComponentKind,
        query: str,
        *,
        limit: int = 20,
    ) -> Iterable[MarketItem]: ...

    def fetch_by_sku(self, sku: str) -> MarketItem | None: ...

    def active_deals(
        self,
        kind: ComponentKind | None = None,
    ) -> Iterable[Deal]: ...


class AdapterRegistry:
    """In-memory registry. Adapters are registered at startup via config."""

    def __init__(self) -> None:
        self._adapters: dict[str, MarketAdapter] = {}

    def register(self, adapter: MarketAdapter) -> None:
        self._adapters[adapter.name] = adapter

    def unregister(self, name: str) -> None:
        self._adapters.pop(name, None)

    def get(self, name: str) -> MarketAdapter:
        if name not in self._adapters:
            raise AdapterUnavailableError(f"adapter '{name}' is not registered")
        return self._adapters[name]

    def available(self) -> tuple[MarketAdapter, ...]:
        return tuple(a for a in self._adapters.values() if a.is_available())

    def all(self) -> tuple[MarketAdapter, ...]:
        return tuple(self._adapters.values())

    def clear(self) -> None:
        self._adapters.clear()


_REGISTRY: AdapterRegistry | None = None


def get_registry() -> AdapterRegistry:
    global _REGISTRY
    if _REGISTRY is None:
        _REGISTRY = AdapterRegistry()
    return _REGISTRY


def reset_registry() -> None:
    """Used by tests. Clears all registered adapters."""
    global _REGISTRY
    _REGISTRY = None
