"""Adapter factory: turn :class:`~pca.core.config.Settings` into a live
:class:`~pca.market.adapter.AdapterRegistry`.

The factory is the **one** place where adapters are constructed with real
HTTP transports. Every other layer (CLI, GUI, web server) receives the
already-built registry, keeping them free of httpx/auth knowledge.

Why a factory and not a simple "new up every adapter" routine? Three
reasons:

1. **Silent-by-default.** Adapters whose credentials are missing are
   simply skipped. Running :command:`pca market-refresh` on a pristine
   install prints a helpful message ("no adapters registered") instead
   of blowing up half-way through a live call.
2. **Explicit opt-in.** Users who have creds set for several retailers
   may still want to restrict a specific run (e.g., "eBay only"). The
   ``PCA_ENABLE_ADAPTERS`` env var takes a comma-separated allow-list.
3. **Testable.** The ``transport_factory`` kwarg is a seam: unit tests
   pass a fake that never imports httpx, so ``pytest-socket`` stays
   happy.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from typing import Any

from pca.core.config import Settings
from pca.core.errors import MarketError
from pca.market.adapter import AdapterRegistry
from pca.market.cache import Cache
from pca.market.plugins import load_plugin_adapters


# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------


Transport = Callable[[str, dict[str, Any]], dict[str, Any]]
"""Signature every retailer adapter accepts: ``(path, params) -> json``."""

TransportFactory = Callable[..., Transport]
"""Callable that builds a concrete :data:`Transport`.

Real callers use :func:`default_transport_factory` (httpx-backed). Tests
pass a stub so no socket is opened.
"""


# ---------------------------------------------------------------------------
# Default httpx transport
# ---------------------------------------------------------------------------


_DEFAULT_CACHE_TTL_SECONDS = 3600  # 1 hour - tuned for "click refresh twice"


def cached_transport(
    inner: Transport,
    *,
    cache: Cache,
    ttl_seconds: int = _DEFAULT_CACHE_TTL_SECONDS,
    namespace: str = "",
) -> Transport:
    """Wrap ``inner`` so identical ``(path, params)`` calls short-circuit.

    - Cache key includes ``namespace`` + a SHA-1 of the JSON-serialized
      ``(path, params)``. We hash so retailer API keys encoded in
      params don't end up plainly visible in the on-disk cache.
    - Exceptions are **not** cached - transient errors get retried on
      the next call.
    """
    def _key(path: str, params: dict[str, Any]) -> str:
        payload = json.dumps(
            {"p": path, "q": params}, sort_keys=True, default=str
        )
        digest = hashlib.sha1(payload.encode("utf-8")).hexdigest()[:20]
        return f"{namespace}:{digest}" if namespace else digest

    def _wrapped(path: str, params: dict[str, Any]) -> dict[str, Any]:
        key = _key(path, params)
        hit = cache.get(key)
        if hit is not None:
            return hit
        value = inner(path, params)  # raises propagate; intentional
        cache.set(key, value, ttl_seconds)
        return value

    return _wrapped


def default_transport_factory(
    base_url: str,
    *,
    timeout_s: float,
    auth: Any | None = None,
    headers: dict[str, str] | None = None,
    cache: bool = True,
    cache_ttl_seconds: int = _DEFAULT_CACHE_TTL_SECONDS,
) -> Transport:
    """Return a :data:`Transport` backed by a singleton ``httpx.Client``.

    The returned callable:

    - Prepends ``base_url`` when ``path`` is a bare endpoint.
    - Uses GET by default - all current first-party adapters are GET-only.
    - Raises :class:`~pca.core.errors.RateLimitedError` on HTTP 429 so
      adapters can surface a clean retry-after message.
    - Raises :class:`~pca.core.errors.MarketError` on other non-2xx
      responses.

    The ``httpx`` import is local so import-time cost is only paid when
    the factory is actually called.
    """
    import httpx  # local - keeps test suites w/o httpx importing this module

    from pca.core.errors import MarketError as _MarketError
    from pca.core.errors import RateLimitedError

    client = httpx.Client(
        base_url=base_url,
        timeout=timeout_s,
        headers=headers or {},
    )

    def _transport(path: str, params: dict[str, Any]) -> dict[str, Any]:
        try:
            resp = client.get(path, params=params, auth=auth)
        except httpx.HTTPError as exc:
            raise _MarketError(f"HTTP error for {path}: {exc}") from exc
        if resp.status_code == 429:
            retry = resp.headers.get("Retry-After", "unknown")
            raise RateLimitedError(f"rate limited by {base_url} (Retry-After={retry})")
        if resp.status_code >= 400:
            raise _MarketError(
                f"{base_url}{path} -> {resp.status_code}: {resp.text[:200]}"
            )
        try:
            return resp.json()
        except ValueError as exc:
            raise _MarketError(f"non-JSON response from {base_url}{path}") from exc

    if not cache:
        return _transport
    # Namespace the cache per base URL so Best Buy / eBay never collide.
    namespace = "http:" + base_url.replace("://", "_").replace("/", "_")
    return cached_transport(
        _transport,
        cache=Cache(namespace),
        ttl_seconds=cache_ttl_seconds,
        namespace=namespace,
    )


# ---------------------------------------------------------------------------
# Adapter construction helpers
# ---------------------------------------------------------------------------


def _resolve_secret(value: Any) -> str | None:
    """Pydantic ``SecretStr`` unwrap, or plain string passthrough."""
    if value is None:
        return None
    if hasattr(value, "get_secret_value"):
        return value.get_secret_value()
    return str(value)


def _parse_allow_list(raw: str) -> frozenset[str]:
    return frozenset(n.strip() for n in raw.split(",") if n.strip())


def _want(name: str, allow_list: frozenset[str]) -> bool:
    """Should we try to register adapter ``name``?

    - Empty allow-list = auto mode = register when creds are present.
    - Non-empty allow-list = register iff ``name`` is in the list.
    """
    if not allow_list:
        return True
    return name in allow_list


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


_BESTBUY_URL = "https://api.bestbuy.com"
_EBAY_URL = "https://api.ebay.com"
_PAAPI_URL = "https://webservices.amazon.com"


def build_registry_from_settings(
    settings: Settings,
    *,
    transport_factory: TransportFactory | None = None,
) -> AdapterRegistry:
    """Construct an :class:`AdapterRegistry` from the given settings.

    Args:
        settings: Loaded :class:`Settings` - supplies retailer credentials
            and the allow-list via ``PCA_ENABLE_ADAPTERS``.
        transport_factory: Advanced injection seam - unit tests pass a
            fake so no real HTTP client is constructed. Defaults to
            :func:`default_transport_factory`.

    Returns:
        A populated :class:`AdapterRegistry`. May be empty if no
        credentials are configured (not an error - that's the valid
        "first-launch" state).

    Raises:
        MarketError: if ``PCA_ENABLE_ADAPTERS`` names an adapter whose
            credentials are missing. We prefer a loud failure here
            because the user explicitly opted in.
    """
    tf = transport_factory or default_transport_factory
    reg = AdapterRegistry()
    allow = _parse_allow_list(settings.enable_adapters)
    timeout = float(getattr(settings, "adapter_http_timeout", 10.0))

    # ------------- Best Buy -------------
    if _want("bestbuy", allow):
        api_key = _resolve_secret(settings.bestbuy_api_key)
        if api_key:
            from pca.market.adapters.bestbuy import BestBuyAdapter

            transport = tf(_BESTBUY_URL, timeout_s=timeout)
            reg.register(BestBuyAdapter(api_key, transport=transport))
        elif "bestbuy" in allow:
            raise MarketError(
                "adapter 'bestbuy' requested but PCA_BESTBUY_API_KEY is not set"
            )

    # ------------- eBay Browse -------------
    if _want("ebay", allow):
        cid = _resolve_secret(settings.ebay_client_id)
        sec = _resolve_secret(settings.ebay_client_secret)
        if cid and sec:
            from pca.market.adapters.ebay import EbayBrowseAdapter

            transport = tf(_EBAY_URL, timeout_s=timeout)
            reg.register(EbayBrowseAdapter(cid, sec, transport=transport))
        elif "ebay" in allow:
            raise MarketError(
                "adapter 'ebay' requested but PCA_EBAY_CLIENT_ID / _SECRET are not set"
            )

    # ------------- eBay Sold (insights) -------------
    if _want("ebay-sold", allow):
        cid = _resolve_secret(settings.ebay_client_id)
        sec = _resolve_secret(settings.ebay_client_secret)
        if cid and sec:
            from pca.market.adapters.ebay_sold import EbaySoldAdapter

            transport = tf(_EBAY_URL, timeout_s=timeout)
            reg.register(EbaySoldAdapter(cid, sec, transport=transport))
        elif "ebay-sold" in allow:
            raise MarketError(
                "adapter 'ebay-sold' requires the same eBay credentials as 'ebay'"
            )

    # ------------- Amazon PA-API 5 (stubbed) -------------
    if _want("amazon-paapi", allow):
        ak = _resolve_secret(settings.amazon_access_key)
        sk = _resolve_secret(settings.amazon_secret_key)
        tag = settings.amazon_assoc_tag  # plain str, not secret
        if ak and sk and tag:
            from pca.market.adapters.amazon_paapi import AmazonPaapiAdapter

            transport = tf(_PAAPI_URL, timeout_s=timeout)
            reg.register(
                AmazonPaapiAdapter(
                    ak,
                    sk,
                    tag,
                    transport=transport,
                    region=settings.amazon_region,
                )
            )
        elif "amazon-paapi" in allow:
            raise MarketError(
                "adapter 'amazon-paapi' requires PCA_AMAZON_ACCESS_KEY, "
                "PCA_AMAZON_SECRET_KEY, and PCA_AMAZON_ASSOC_TAG"
            )

    # ------------- Newegg affiliate feed (local file only) -------------
    if _want("newegg", allow):
        feed = settings.newegg_feed_path
        if feed is not None and feed.exists():
            from pca.market.adapters.newegg import NeweggFeedAdapter

            reg.register(NeweggFeedAdapter(feed))
        elif "newegg" in allow:
            raise MarketError(
                "adapter 'newegg' requested but PCA_NEWEGG_FEED_PATH is missing or invalid"
            )

    # ------------- Plugins (opt-in) -------------
    if settings.allow_plugins:
        for plugin in load_plugin_adapters(settings):
            for adapter in plugin.adapters:
                if _want(getattr(adapter, "name", plugin.name), allow):
                    reg.register(adapter)

    return reg


__all__ = [
    "Transport",
    "TransportFactory",
    "build_registry_from_settings",
    "default_transport_factory",
]
