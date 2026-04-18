"""Retailer plugin SDK.

Third parties expose a ``MarketAdapter`` factory under the
``pc_upgrade_advisor.market_adapters`` entry-point group. At startup we call
:func:`load_plugin_adapters` which discovers every installed plugin, invokes
its factory with the runtime settings, and registers the returned adapter(s)
with the :class:`~pca.market.adapter.AdapterRegistry`.

Plugin authors must:

1. Declare an entry point in their ``pyproject.toml``::

       [project.entry-points."pc_upgrade_advisor.market_adapters"]
       acme = "acme_pca_plugin:build_adapter"

2. Implement a ``build_adapter(settings: Settings) -> MarketAdapter | Iterable[MarketAdapter]``
   factory returning one or more adapters.

3. Pass :func:`check_conformance` against their adapter in their own tests.

Plugins run **in-process**, so they have the same authority as the host. We
give them no sandbox - plugin authors are expected to ship trusted code. See
``docs/adr/0012-plugin-sdk.md`` for the threat model.
"""

from __future__ import annotations

import importlib
import importlib.metadata as ilm
import inspect
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, Protocol

from pca.core.errors import MarketError
from pca.core.models import ComponentKind, Deal, MarketItem

ENTRY_POINT_GROUP = "pc_upgrade_advisor.market_adapters"


class MarketAdapterFactory(Protocol):
    """Signature every plugin must honor."""

    def __call__(self, settings: Any) -> Any: ...


@dataclass(frozen=True)
class LoadedPlugin:
    """Metadata + instances for a loaded plugin."""

    name: str
    dist: str | None
    adapters: tuple[Any, ...]


def load_plugin_adapters(settings: Any) -> tuple[LoadedPlugin, ...]:
    """Discover, import, and instantiate every installed plugin.

    Returns a tuple of ``LoadedPlugin`` - callers choose whether to register
    them via :meth:`AdapterRegistry.register`.
    """
    loaded: list[LoadedPlugin] = []
    try:
        eps = ilm.entry_points(group=ENTRY_POINT_GROUP)
    except TypeError:  # pragma: no cover - python < 3.10
        eps = [e for e in ilm.entry_points().get(ENTRY_POINT_GROUP, [])]
    for ep in eps:
        try:
            factory = ep.load()
        except Exception as exc:  # noqa: BLE001 - plugin boundary
            raise MarketError(f"failed to load plugin '{ep.name}': {exc}") from exc
        adapters = _invoke_factory(factory, settings, ep.name)
        loaded.append(
            LoadedPlugin(
                name=ep.name,
                dist=getattr(ep, "dist", None) and ep.dist.name,  # type: ignore[union-attr]
                adapters=adapters,
            )
        )
    return tuple(loaded)


def _invoke_factory(factory: Any, settings: Any, name: str) -> tuple[Any, ...]:
    if not callable(factory):
        raise MarketError(f"plugin '{name}' entry point is not callable")
    try:
        result = factory(settings)
    except Exception as exc:  # noqa: BLE001 - plugin boundary
        raise MarketError(f"plugin '{name}' factory failed: {exc}") from exc
    if inspect.isawaitable(result):  # pragma: no cover - async not supported yet
        raise MarketError(f"plugin '{name}' returned an awaitable; not supported")
    if isinstance(result, Iterable) and not isinstance(result, (str, bytes)):
        adapters = tuple(result)
    else:
        adapters = (result,)
    for a in adapters:
        _validate_surface(a, name)
    return adapters


def _validate_surface(adapter: Any, plugin_name: str) -> None:
    """Cheap duck-type check. The real conformance test is :func:`check_conformance`."""
    required = ("name", "is_available", "search", "fetch_by_sku", "active_deals")
    missing = [m for m in required if not hasattr(adapter, m)]
    if missing:
        raise MarketError(
            f"plugin '{plugin_name}' adapter missing: {', '.join(missing)}"
        )
    if not isinstance(getattr(adapter, "name", None), str):
        raise MarketError(f"plugin '{plugin_name}' adapter.name must be a str")


# ---------------------------------------------------------------------------
# Conformance test harness - runnable from plugin test suites
# ---------------------------------------------------------------------------


class ConformanceError(AssertionError):
    """Raised by :func:`check_conformance` when an adapter misbehaves."""


def check_conformance(adapter: Any) -> None:
    """Assert that ``adapter`` obeys the :class:`MarketAdapter` contract.

    This function is intentionally executable by plugin authors from their
    own test suites - import it and call it, nothing more. We exercise every
    method with inputs that must NOT touch the network (kind/query with no
    matches, a nonexistent SKU, etc.).
    """
    _validate_surface(adapter, adapter.__class__.__name__)

    if not hasattr(adapter, "is_available"):
        raise ConformanceError("adapter lacks is_available()")

    # search must return an iterable of MarketItem (possibly empty).
    items = list(adapter.search(ComponentKind.CPU, "__nonexistent__query__", limit=1))
    for it in items:
        if not isinstance(it, MarketItem):
            raise ConformanceError(f"search returned non-MarketItem: {type(it)!r}")

    # fetch_by_sku must return MarketItem or None.
    result = adapter.fetch_by_sku("__nonexistent__sku__")
    if result is not None and not isinstance(result, MarketItem):
        raise ConformanceError(f"fetch_by_sku returned {type(result)!r}")

    # active_deals must return an iterable of Deal.
    deals = list(adapter.active_deals(None))
    for d in deals:
        if not isinstance(d, Deal):
            raise ConformanceError(f"active_deals returned non-Deal: {type(d)!r}")


# ---------------------------------------------------------------------------
# Minimal "hello world" plugin that ships in-tree for testing
# ---------------------------------------------------------------------------


class _ExamplePlugin:
    """Trivial adapter that returns a single fixed MarketItem.

    We use it in the conformance test suite to prove the whole plumbing works
    end-to-end without needing a real retailer's credentials.
    """

    name = "example-plugin"

    def __init__(self, marker: str = "example") -> None:
        self._marker = marker

    def is_available(self) -> bool:
        return True

    def search(
        self,
        kind: ComponentKind,
        query: str,
        *,
        limit: int = 20,
    ) -> Iterable[MarketItem]:
        if kind is not ComponentKind.CPU or not query:
            return ()
        return (
            MarketItem(
                sku=f"EX-{self._marker}-1",
                kind=ComponentKind.CPU,
                vendor="Example",
                model=f"Example CPU for '{query[:40]}'",
                price_usd=Decimal("199.99"),
                source=self.name,
                url="https://example.invalid/cpu",
                fetched_at=datetime.now(UTC),
            ),
        )

    def fetch_by_sku(self, sku: str) -> MarketItem | None:
        if sku.startswith(f"EX-{self._marker}-"):
            return MarketItem(
                sku=sku,
                kind=ComponentKind.CPU,
                vendor="Example",
                model="Example CPU",
                price_usd=Decimal("199.99"),
                source=self.name,
                url="https://example.invalid/cpu",
                fetched_at=datetime.now(UTC),
            )
        return None

    def active_deals(
        self,
        kind: ComponentKind | None = None,
    ) -> Iterable[Deal]:
        return ()


def build_example_adapter(settings: Any) -> Any:
    """Factory matching the plugin contract; used by the unit tests."""
    return _ExamplePlugin()


def import_and_build(dotted: str, settings: Any) -> Any:
    """Helper for tests: load ``module:attr`` and invoke as a factory."""
    module, _, attr = dotted.partition(":")
    mod = importlib.import_module(module)
    factory = getattr(mod, attr)
    return factory(settings)


__all__ = [
    "ConformanceError",
    "ENTRY_POINT_GROUP",
    "LoadedPlugin",
    "MarketAdapterFactory",
    "build_example_adapter",
    "check_conformance",
    "import_and_build",
    "load_plugin_adapters",
]
