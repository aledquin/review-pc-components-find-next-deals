"""Market-data refresh orchestrator.

Given a :class:`SystemSnapshot` and a populated
:class:`~pca.market.adapter.AdapterRegistry`, this module:

1. Builds a search query per :class:`ComponentKind` that we actually
   want to suggest replacements for (CPU / GPU / RAM / storage / PSU /
   cooler / motherboard).
2. Calls every registered **available** adapter's ``.search()`` method
   with each query.
3. Merges results into a deduplicated tuple of :class:`MarketItem`,
   collecting any per-adapter errors for partial-success reporting.
4. Optionally writes the merged bundle to disk in the same format the
   ``--market`` flag and the bundled default consume.

Design notes
------------
- **No network in this module.** Adapters own their own HTTP clients;
  here we just iterate.
- **Partial success.** One 429 from eBay should not destroy results
  from Best Buy. Errors are returned in ``RefreshResult.errors`` as
  plain strings so the caller can render them in a warning pill.
- **Thread-safe.** Called from a Qt worker thread in the GUI and from
  a FastAPI background task on the web dashboard. The module is
  stateless.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pca.core.errors import MarketError
from pca.core.models import (
    ComponentKind,
    Deal,
    MarketItem,
    SystemSnapshot,
)
from pca.market.adapter import AdapterRegistry


# ---------------------------------------------------------------------------
# Query generation
# ---------------------------------------------------------------------------


_KIND_FALLBACK_QUERIES: dict[ComponentKind, list[str]] = {
    ComponentKind.CPU: ["desktop CPU", "gaming CPU", "ryzen 7", "core i7"],
    ComponentKind.GPU: ["graphics card", "GPU", "rtx 4060", "radeon rx 7700"],
    ComponentKind.RAM: ["DDR4 memory", "DDR5 memory"],
    ComponentKind.STORAGE: ["NVMe SSD 1TB", "NVMe SSD 2TB"],
    ComponentKind.PSU: ["ATX power supply 650W", "ATX PSU 850W gold"],
    ComponentKind.COOLER: ["CPU air cooler", "CPU AIO 240mm"],
    ComponentKind.MOTHERBOARD: ["motherboard"],
}


_SAME_KIND_UPGRADE_KINDS: tuple[ComponentKind, ...] = (
    ComponentKind.CPU,
    ComponentKind.GPU,
    ComponentKind.RAM,
    ComponentKind.STORAGE,
    ComponentKind.PSU,
    ComponentKind.COOLER,
    ComponentKind.MOTHERBOARD,
)


def build_queries(snapshot: SystemSnapshot) -> dict[ComponentKind, list[str]]:
    """Return a query list per upgradable ``ComponentKind``.

    Queries are derived from the currently installed component's specs
    (RAM type, socket, etc.) with sensible fallbacks per kind if the
    spec data is thin.
    """
    out: dict[ComponentKind, list[str]] = {}

    for kind in _SAME_KIND_UPGRADE_KINDS:
        queries: list[str] = []
        for comp in snapshot.components_of(kind):
            specs: dict[str, Any] = dict(comp.specs or {})
            q = _query_for_kind(kind, comp.vendor, comp.model, specs)
            if q:
                queries.append(q)
        if not queries:
            queries = list(_KIND_FALLBACK_QUERIES.get(kind, []))
        # Dedupe while keeping order.
        seen: set[str] = set()
        uniq: list[str] = []
        for q in queries:
            key = q.lower().strip()
            if key and key not in seen:
                seen.add(key)
                uniq.append(q.strip())
        if uniq:
            out[kind] = uniq
    return out


def _query_for_kind(
    kind: ComponentKind, vendor: str, model: str, specs: dict[str, Any]
) -> str:
    """Hand-rolled heuristic - keeps the queries short and retailer-friendly."""
    if kind is ComponentKind.RAM:
        t = str(specs.get("type", "")).strip()
        cap = specs.get("capacity_gb")
        speed = specs.get("speed_mts")
        parts = [p for p in (t, f"{cap}GB" if cap else "", f"{speed}MT/s" if speed else "") if p]
        return " ".join(parts) if parts else "DDR4 memory"
    if kind is ComponentKind.CPU:
        socket = specs.get("socket")
        if socket:
            return f"CPU {socket}"
        return "desktop CPU"
    if kind is ComponentKind.GPU:
        return "graphics card"
    if kind is ComponentKind.STORAGE:
        iface = specs.get("interface") or "NVMe"
        cap = specs.get("capacity_gb")
        if cap:
            return f"{iface} SSD {cap}GB"
        return f"{iface} SSD"
    if kind is ComponentKind.PSU:
        watts = specs.get("watts")
        return f"ATX power supply {watts}W" if watts else "ATX PSU gold"
    if kind is ComponentKind.COOLER:
        kind_hint = specs.get("kind") or "air"
        return f"CPU {kind_hint} cooler"
    if kind is ComponentKind.MOTHERBOARD:
        socket = specs.get("socket")
        return f"motherboard {socket}" if socket else "motherboard"
    return model


# ---------------------------------------------------------------------------
# Refresh result
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RefreshResult:
    """Outcome of one :func:`refresh_market` invocation."""

    items: tuple[MarketItem, ...]
    deals: tuple[Deal, ...]
    sources: tuple[str, ...]
    errors: tuple[str, ...]
    generated_at: datetime

    def is_success(self) -> bool:
        return bool(self.items) and not self.errors


# ---------------------------------------------------------------------------
# The orchestrator
# ---------------------------------------------------------------------------


def refresh_market(
    snapshot: SystemSnapshot,
    registry: AdapterRegistry,
    *,
    per_kind_limit: int = 20,
) -> RefreshResult:
    """Iterate every available adapter, merge search results.

    Args:
        snapshot: the user's current rig - drives query generation.
        registry: populated adapter registry. Unavailable adapters
            (missing credentials, offline flag) are skipped.
        per_kind_limit: max items per (adapter, kind) pair. The adapter
            may return fewer.

    Returns:
        A :class:`RefreshResult` containing every merged ``MarketItem``,
        deduplicated by ``(source, sku)``.

    Raises:
        MarketError: if ``registry`` is empty or every adapter is
            unavailable. Individual adapter failures do NOT raise - they
            populate ``RefreshResult.errors``.
    """
    all_adapters = registry.all()
    if not all_adapters:
        raise MarketError("no adapters registered - configure retailer credentials")

    live = [a for a in all_adapters if a.is_available()]
    if not live:
        raise MarketError(
            "no adapters available - check your API keys "
            "(PCA_BESTBUY_API_KEY, PCA_EBAY_CLIENT_ID, ...)"
        )

    queries_by_kind = build_queries(snapshot)
    merged: dict[tuple[str, str], MarketItem] = {}
    sources: set[str] = set()
    errors: list[str] = []
    deals: list[Deal] = []

    for adapter in live:
        sources.add(adapter.name)
        try:
            for kind, queries in queries_by_kind.items():
                for q in queries:
                    for item in adapter.search(kind, q, limit=per_kind_limit):
                        merged.setdefault((item.source, item.sku), item)
            for deal in adapter.active_deals():
                deals.append(deal)
        except Exception as exc:
            errors.append(f"{adapter.name}: {exc}")

    return RefreshResult(
        items=tuple(merged.values()),
        deals=tuple(deals),
        sources=tuple(sorted(sources)),
        errors=tuple(errors),
        generated_at=datetime.now(UTC),
    )


# ---------------------------------------------------------------------------
# Persistence + age helpers
# ---------------------------------------------------------------------------


def write_market_snapshot(
    result: RefreshResult,
    path: Path,
    *,
    identifier: str = "refreshed_market",
) -> Path:
    """Dump ``result`` to ``path`` in the ``MarketSnapshot`` JSON format
    (the same format ``resources/market/default_market.json`` uses and
    the ``--market`` flag accepts)."""
    import json

    payload = {
        "id": identifier,
        "generated_at": result.generated_at.isoformat(),
        "sources": list(result.sources),
        "items": [json.loads(i.model_dump_json()) for i in result.items],
        "deals": [json.loads(d.model_dump_json()) for d in result.deals],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path


def market_snapshot_age_days(generated_at: datetime) -> int:
    """Return whole days between ``generated_at`` and now (UTC).

    Accepts naive datetimes and treats them as UTC - important because
    older snapshots in the repo use bare ISO strings.
    """
    if generated_at.tzinfo is None:
        generated_at = generated_at.replace(tzinfo=UTC)
    delta = datetime.now(UTC) - generated_at
    return max(0, int(delta.total_seconds() // 86400))
