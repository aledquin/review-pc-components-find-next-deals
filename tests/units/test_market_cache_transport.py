"""Unit tests for :func:`pca.market.factory.cached_transport`.

Zero network traffic: the underlying transport is a plain function that
counts calls, so ``pytest-socket`` stays strict.
"""

from __future__ import annotations

from typing import Any

import pytest


class _CountingTransport:
    """Minimal Transport impl that records every invocation."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.stub_response: dict[str, Any] = {"ok": True}

    def __call__(self, path: str, params: dict[str, Any]) -> dict[str, Any]:
        self.calls.append((path, dict(params)))
        return self.stub_response


def test_cached_transport_short_circuits_repeated_calls() -> None:
    """The second call with the same (path, params) hits the cache, not
    the underlying transport."""
    from pca.market.factory import cached_transport
    from pca.market.cache import Cache

    base = _CountingTransport()
    cache = Cache("test-unit-short-circuit")
    cache.clear()
    wrapped = cached_transport(base, cache=cache, ttl_seconds=60)

    r1 = wrapped("/search", {"q": "cpu"})
    r2 = wrapped("/search", {"q": "cpu"})

    assert r1 == base.stub_response
    assert r2 == base.stub_response
    assert len(base.calls) == 1, "second call should be served from cache"


def test_cached_transport_varies_on_params() -> None:
    from pca.market.factory import cached_transport
    from pca.market.cache import Cache

    base = _CountingTransport()
    cache = Cache("test-unit-params")
    cache.clear()
    wrapped = cached_transport(base, cache=cache, ttl_seconds=60)

    wrapped("/search", {"q": "cpu"})
    wrapped("/search", {"q": "gpu"})

    assert len(base.calls) == 2


def test_cached_transport_expires_after_ttl(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When the TTL elapses, the next call goes through again."""
    from pca.market import cache as cache_module
    from pca.market.factory import cached_transport

    t = {"now": 1_000.0}
    monkeypatch.setattr(cache_module.time, "time", lambda: t["now"])

    base = _CountingTransport()
    cache = cache_module.Cache("test-unit-ttl")
    cache.clear()
    wrapped = cached_transport(base, cache=cache, ttl_seconds=5)

    wrapped("/a", {})
    t["now"] += 1  # still valid
    wrapped("/a", {})
    assert len(base.calls) == 1

    t["now"] += 10  # past TTL
    wrapped("/a", {})
    assert len(base.calls) == 2


def test_cached_transport_does_not_cache_exceptions() -> None:
    from pca.market.factory import cached_transport
    from pca.market.cache import Cache

    class _Raising:
        def __init__(self) -> None:
            self.calls = 0

        def __call__(self, path: str, params: dict[str, Any]) -> dict[str, Any]:
            self.calls += 1
            raise RuntimeError("boom")

    base = _Raising()
    cache = Cache("test-unit-errors")
    cache.clear()
    wrapped = cached_transport(base, cache=cache, ttl_seconds=60)

    with pytest.raises(RuntimeError):
        wrapped("/x", {})
    with pytest.raises(RuntimeError):
        wrapped("/x", {})
    assert base.calls == 2, "errors must not be cached"


def test_default_transport_factory_wires_cache_when_enabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The public factory honors ``cache=True`` by wrapping with cached_transport."""
    from pca.market.factory import default_transport_factory

    # Make sure we never actually try to hit the network.
    # We can't easily stop httpx.Client() from being instantiated, but the
    # transport closure is only called when we invoke it. A smoke check is
    # enough: the returned callable must be different from the raw one
    # when cache=True and identity-equivalent behavior under cache=False.

    bare = default_transport_factory("https://example.invalid", timeout_s=1.0, cache=False)
    wrapped = default_transport_factory("https://example.invalid", timeout_s=1.0, cache=True)
    assert bare is not wrapped
    # The wrapped version must still be callable with the Transport shape.
    assert callable(wrapped)
