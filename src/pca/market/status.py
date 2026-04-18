"""Retailer adapter status / health report.

Answers the question the user cares about when Recommend returns
"no adapters available": *which* adapters would activate under the
current environment, and if not, *why*.

Two public helpers:

- :func:`describe_adapter_status` inspects :class:`~pca.core.config.Settings`
  and returns a tuple of :class:`AdapterStatus` - one row per
  first-party adapter. Pure introspection, no network.
- :func:`format_status_table` turns that report into a readable multi-line
  string suitable for the CLI (``pca doctor``) or a web fragment.

The web dashboard, the GUI status bar, and the CLI all consume the same
data so explanations stay consistent across surfaces.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pca.core.config import Settings


@dataclass(frozen=True)
class AdapterStatus:
    """One row of the adapter status report."""

    name: str
    active: bool
    reason: str
    """Human-readable explanation - always mentions the env vars a user
    would need to change to flip ``active``."""

    required_env: tuple[str, ...] = ()
    """Env vars the adapter needs. Useful for UI tooltips."""


def _allow(raw: str) -> frozenset[str]:
    return frozenset(n.strip() for n in raw.split(",") if n.strip())


def _excluded_by_allow_list(name: str, allow: frozenset[str]) -> str | None:
    if allow and name not in allow:
        return (
            f"excluded by allow-list PCA_ENABLE_ADAPTERS='{','.join(sorted(allow))}'"
        )
    return None


def _resolve_secret(value: Any) -> str | None:
    if value is None:
        return None
    if hasattr(value, "get_secret_value"):
        return value.get_secret_value()
    return str(value)


def describe_adapter_status(settings: Settings) -> tuple[AdapterStatus, ...]:
    """Return one :class:`AdapterStatus` per first-party adapter.

    Plugins are not included here - they are discovered lazily by
    :func:`~pca.market.plugins.load_plugin_adapters` and don't have a
    stable env-var surface to report on.
    """
    allow = _allow(settings.enable_adapters)
    out: list[AdapterStatus] = []

    # ---------- Best Buy ----------
    excl = _excluded_by_allow_list("bestbuy", allow)
    if excl:
        out.append(
            AdapterStatus(
                "bestbuy", False, excl, ("PCA_BESTBUY_API_KEY",)
            )
        )
    elif _resolve_secret(settings.bestbuy_api_key):
        out.append(
            AdapterStatus(
                "bestbuy",
                True,
                "configured (PCA_BESTBUY_API_KEY is set)",
                ("PCA_BESTBUY_API_KEY",),
            )
        )
    else:
        out.append(
            AdapterStatus(
                "bestbuy",
                False,
                "missing PCA_BESTBUY_API_KEY - sign up at developer.bestbuy.com",
                ("PCA_BESTBUY_API_KEY",),
            )
        )

    # ---------- eBay Browse ----------
    ebay_env = ("PCA_EBAY_CLIENT_ID", "PCA_EBAY_CLIENT_SECRET")
    excl = _excluded_by_allow_list("ebay", allow)
    if excl:
        out.append(AdapterStatus("ebay", False, excl, ebay_env))
    else:
        cid = _resolve_secret(settings.ebay_client_id)
        sec = _resolve_secret(settings.ebay_client_secret)
        if cid and sec:
            out.append(
                AdapterStatus("ebay", True, "configured (OAuth client ready)", ebay_env)
            )
        elif cid and not sec:
            out.append(
                AdapterStatus(
                    "ebay",
                    False,
                    "PCA_EBAY_CLIENT_ID set but PCA_EBAY_CLIENT_SECRET missing",
                    ebay_env,
                )
            )
        elif sec and not cid:
            out.append(
                AdapterStatus(
                    "ebay",
                    False,
                    "PCA_EBAY_CLIENT_SECRET set but PCA_EBAY_CLIENT_ID missing",
                    ebay_env,
                )
            )
        else:
            out.append(
                AdapterStatus(
                    "ebay",
                    False,
                    "missing PCA_EBAY_CLIENT_ID and PCA_EBAY_CLIENT_SECRET",
                    ebay_env,
                )
            )

    # ---------- eBay Sold (same creds) ----------
    excl = _excluded_by_allow_list("ebay-sold", allow)
    if excl:
        out.append(AdapterStatus("ebay-sold", False, excl, ebay_env))
    else:
        cid = _resolve_secret(settings.ebay_client_id)
        sec = _resolve_secret(settings.ebay_client_secret)
        if cid and sec:
            out.append(
                AdapterStatus(
                    "ebay-sold",
                    True,
                    "configured (shares credentials with 'ebay')",
                    ebay_env,
                )
            )
        else:
            out.append(
                AdapterStatus(
                    "ebay-sold",
                    False,
                    "missing PCA_EBAY_CLIENT_ID / PCA_EBAY_CLIENT_SECRET "
                    "(shares credentials with 'ebay')",
                    ebay_env,
                )
            )

    # ---------- Amazon PA-API ----------
    paapi_env = (
        "PCA_AMAZON_ACCESS_KEY",
        "PCA_AMAZON_SECRET_KEY",
        "PCA_AMAZON_ASSOC_TAG",
    )
    excl = _excluded_by_allow_list("amazon-paapi", allow)
    if excl:
        out.append(AdapterStatus("amazon-paapi", False, excl, paapi_env))
    else:
        ak = _resolve_secret(settings.amazon_access_key)
        sk = _resolve_secret(settings.amazon_secret_key)
        tag = settings.amazon_assoc_tag
        if ak and sk and tag:
            out.append(
                AdapterStatus(
                    "amazon-paapi",
                    True,
                    f"configured for associate tag '{tag}' in region "
                    f"{settings.amazon_region}",
                    paapi_env,
                )
            )
        else:
            missing = [e for e, v in zip(paapi_env, (ak, sk, tag), strict=True) if not v]
            out.append(
                AdapterStatus(
                    "amazon-paapi",
                    False,
                    "missing: " + ", ".join(missing),
                    paapi_env,
                )
            )

    # ---------- Newegg (local file only) ----------
    newegg_env = ("PCA_NEWEGG_FEED_PATH",)
    excl = _excluded_by_allow_list("newegg", allow)
    if excl:
        out.append(AdapterStatus("newegg", False, excl, newegg_env))
    else:
        feed = settings.newegg_feed_path
        if feed is not None and feed.exists():
            out.append(
                AdapterStatus(
                    "newegg",
                    True,
                    f"using local feed at {feed}",
                    newegg_env,
                )
            )
        elif feed is not None:
            out.append(
                AdapterStatus(
                    "newegg",
                    False,
                    f"PCA_NEWEGG_FEED_PATH={feed} does not exist",
                    newegg_env,
                )
            )
        else:
            out.append(
                AdapterStatus(
                    "newegg",
                    False,
                    "missing PCA_NEWEGG_FEED_PATH (local file only - scraping not supported)",
                    newegg_env,
                )
            )

    return tuple(out)


def format_status_table(report: tuple[AdapterStatus, ...]) -> str:
    """Render ``report`` as a fixed-width multi-line table."""
    name_w = max((len(r.name) for r in report), default=8)
    name_w = max(name_w, len("Adapter"))
    header = (
        f"{'Adapter'.ljust(name_w)}  {'State'.ljust(8)}  Detail\n"
        f"{'-' * name_w}  {'-' * 8}  {'-' * 40}"
    )
    lines = [header]
    for row in report:
        state = "active" if row.active else "inactive"
        lines.append(f"{row.name.ljust(name_w)}  {state.ljust(8)}  {row.reason}")
    active_count = sum(1 for r in report if r.active)
    lines.append("")
    lines.append(
        f"Summary: {active_count}/{len(report)} first-party adapters active."
    )
    return "\n".join(lines)


__all__ = [
    "AdapterStatus",
    "describe_adapter_status",
    "format_status_table",
]
