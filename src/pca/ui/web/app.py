"""FastAPI application for the local dashboard.

Endpoints are intentionally small. The web UI is a thin skin over the same
orchestrator the CLI uses - no business logic lives here.

The HTMX + Alpine.js frontend is returned by ``/``; all interactive panels are
driven by ``/htmx/*`` partials so the UI works without a JS build step.

Security posture:

- Defaults to ``127.0.0.1``. LAN mode (``--bind 0.0.0.0``) requires a token.
- No cookies, no sessions, no user-supplied file paths. All inputs validated
  via Pydantic.
- The quote endpoint returns the Quote JSON; HTML/PDF generation goes through
  the existing reporting builder.
"""

from __future__ import annotations

import html
import json
from decimal import Decimal
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from jinja2 import Environment, FileSystemLoader, StrictUndefined, select_autoescape
from pydantic import BaseModel, Field

from pca.budget.optimizer_greedy import optimize_greedy
from pca.budget.optimizer_ilp import optimize_ilp
from pca.budget.optimizer_multi import optimize_multi
from pca.core.models import (
    BudgetConstraint,
    ComponentKind,
    MarketItem,
    SystemSnapshot,
    Workload,
)
from pca.core.resources import resource_path
from pca.deprecation.rules import evaluate_all
from pca.inventory.probe import detect_probe
from pca.quoting.builder import build_quote
from pca.ui.common import (
    fmt_spec_value as _fmt_spec_value,
    safe_external_url as _safe_external_url,
    spec_label as _spec_label,
)


class ServerConfig(BaseModel):
    """Injected settings. Passed to ``create_app`` for easy testing."""

    model_config = {"arbitrary_types_allowed": True}

    snapshot_path: Path | None = None
    market_path: Path | None = None
    lan_token: str | None = None
    ui_disclaimer: str = (
        "Local preview - data does not leave this machine by default."
    )


# ---------------------------------------------------------------------------
# Request/response DTOs
# ---------------------------------------------------------------------------


class RecommendRequest(BaseModel):
    budget_usd: Decimal = Field(gt=Decimal("0"))
    workload: Workload = Workload.GAMING_1440P
    strategy: str = "greedy"
    socket: str | None = None
    ram_type: str | None = None


class UpgradeItemDTO(BaseModel):
    kind: ComponentKind
    vendor: str
    model: str
    price_usd: Decimal
    perf_uplift_pct: float
    rationale: str
    # Click-through to the retailer product page (may be the retailer's
    # storefront root if the adapter cannot resolve a per-SKU URL).
    url: str | None = None
    # Adapter/retailer name: 'bestbuy', 'amazon-paapi', 'ebay', ...
    source: str | None = None
    # Context to visualize *what* is being upgraded. Populated from the
    # current SystemSnapshot when available so the UI can render a
    # side-by-side spec diff without re-querying the server.
    current_vendor: str | None = None
    current_model: str | None = None
    current_specs: dict[str, Any] = Field(default_factory=dict)
    new_specs: dict[str, Any] = Field(default_factory=dict)


class RecommendResponse(BaseModel):
    strategy: str
    total_usd: Decimal
    overall_perf_uplift_pct: float
    items: list[UpgradeItemDTO]


# ---------------------------------------------------------------------------
# Jinja environment for the dashboard shell
# ---------------------------------------------------------------------------


def _env() -> Environment:
    return Environment(
        loader=FileSystemLoader(str(resource_path("templates"))),
        autoescape=select_autoescape(["html", "xml"]),
        undefined=StrictUndefined,
        trim_blocks=True,
        lstrip_blocks=True,
    )


def _pick_optimizer(strategy: str):
    if strategy == "ilp":
        return optimize_ilp
    if strategy == "multi":
        return optimize_multi
    return optimize_greedy


# ---------------------------------------------------------------------------
# App factory
# ---------------------------------------------------------------------------


def create_app(config: ServerConfig | None = None) -> FastAPI:
    cfg = config or ServerConfig()
    app = FastAPI(
        title="PC Upgrade Advisor",
        version="0.3.0",
        docs_url="/api",
    )
    # In-memory override. When the user hits "Detect this PC", we populate
    # this and prefer it over the on-disk ``cfg.snapshot_path``.
    app.state.detected_snapshot = None  # type: SystemSnapshot | None

    def _require_token(request: Request) -> None:
        if cfg.lan_token is None:
            return
        client = request.client.host if request.client else ""
        if client in {"127.0.0.1", "::1"}:
            return
        token = request.headers.get("x-pca-token")
        if token != cfg.lan_token:
            raise HTTPException(status_code=401, detail="invalid token")

    def _load_snapshot() -> SystemSnapshot:
        if app.state.detected_snapshot is not None:
            return app.state.detected_snapshot
        if cfg.snapshot_path and cfg.snapshot_path.exists():
            return SystemSnapshot.model_validate_json(
                cfg.snapshot_path.read_text(encoding="utf-8")
            )
        raise HTTPException(status_code=404, detail="snapshot not configured")

    def _load_market() -> tuple[tuple[MarketItem, ...], tuple[Any, ...]]:
        from pca.core.models import Deal

        # In-memory refresh result wins over disk.
        cached = getattr(app.state, "refreshed_market", None)
        if cached is not None:
            return cached["items"], cached["deals"]

        source: Path | None = None
        if cfg.market_path and cfg.market_path.exists():
            source = cfg.market_path
        else:
            # Fall back to the bundled default catalog.
            default = Path(resource_path("market", "default_market.json"))
            if default.is_file():
                source = default
        if source is None:
            raise HTTPException(status_code=404, detail="market not configured")
        raw = json.loads(source.read_text(encoding="utf-8"))
        items = tuple(MarketItem.model_validate(i) for i in raw.get("items", []))
        deals = tuple(Deal.model_validate(d) for d in raw.get("deals", []))
        return items, deals

    # -----------------------------------------------------------------
    # Routes
    # -----------------------------------------------------------------

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/", response_class=HTMLResponse, dependencies=[Depends(_require_token)])
    def index() -> str:
        from pca.market.refresh import market_snapshot_age_days

        market_age: int | None = None
        market_source = "bundled default"
        try:
            cached = getattr(app.state, "refreshed_market", None)
            if cached is not None:
                market_age = market_snapshot_age_days(cached["generated_at"])
                market_source = ", ".join(cached["sources"]) or "live refresh"
            else:
                # Read generated_at off the configured or bundled file.
                path: Path | None = None
                if cfg.market_path and cfg.market_path.exists():
                    path = cfg.market_path
                    market_source = "configured file"
                else:
                    p = Path(resource_path("market", "default_market.json"))
                    if p.is_file():
                        path = p
                if path is not None:
                    from datetime import datetime as _dt

                    raw = json.loads(path.read_text(encoding="utf-8"))
                    ts = raw.get("generated_at")
                    if ts:
                        market_age = market_snapshot_age_days(
                            _dt.fromisoformat(ts.replace("Z", "+00:00"))
                        )
        except Exception:
            market_age = None

        tmpl = _env().get_template("dashboard.html.j2")
        return tmpl.render(
            disclaimer=cfg.ui_disclaimer,
            market_age_days=market_age,
            market_source=market_source,
            market_is_stale=(market_age is not None and market_age > 14),
        )

    @app.get(
        "/api/inventory",
        response_class=JSONResponse,
        dependencies=[Depends(_require_token)],
    )
    def api_inventory() -> dict[str, Any]:
        snap = _load_snapshot()
        deprecations = evaluate_all(snap)
        payload = json.loads(snap.model_dump_json())
        payload["deprecations"] = deprecations
        return payload

    @app.post(
        "/api/detect",
        response_class=JSONResponse,
        dependencies=[Depends(_require_token)],
    )
    def api_detect() -> dict[str, Any]:
        """Inspect the *local* host and cache the snapshot on the app.

        Subsequent calls to ``/api/inventory`` or the HTMX fragments
        will see the detected snapshot until the process restarts.
        """
        try:
            probe = detect_probe()
            snap = probe.collect()
        except Exception as exc:  # surface to the client
            raise HTTPException(status_code=500, detail=f"probe failed: {exc}")
        app.state.detected_snapshot = snap
        deprecations = evaluate_all(snap)
        payload = json.loads(snap.model_dump_json())
        payload["deprecations"] = deprecations
        return payload

    @app.post(
        "/api/market/refresh",
        response_class=JSONResponse,
        dependencies=[Depends(_require_token)],
    )
    def api_market_refresh() -> dict[str, Any]:
        """Query every configured retailer adapter and cache the result.

        The refreshed catalog replaces whatever was loaded from disk for
        the remainder of this server's lifetime. Subsequent
        ``/api/recommend`` and quote calls use the fresh data
        automatically.
        """
        from pca.core.config import get_settings
        from pca.market.factory import build_registry_from_settings
        from pca.market.refresh import refresh_market

        try:
            snap = _load_snapshot()
        except HTTPException:
            raise HTTPException(
                status_code=409,
                detail=(
                    "snapshot required before refresh - POST /api/detect "
                    "or start the server with --snapshot"
                ),
            )
        try:
            registry = build_registry_from_settings(get_settings())
            result = refresh_market(snap, registry)
        except Exception as exc:
            raise HTTPException(status_code=502, detail=str(exc))
        app.state.refreshed_market = {
            "items": result.items,
            "deals": result.deals,
            "generated_at": result.generated_at,
            "sources": result.sources,
            "errors": result.errors,
        }
        return {
            "generated_at": result.generated_at.isoformat(),
            "item_count": len(result.items),
            "sources": list(result.sources),
            "errors": list(result.errors),
        }

    @app.post(
        "/htmx/market/refresh",
        response_class=HTMLResponse,
        dependencies=[Depends(_require_token)],
    )
    def htmx_market_refresh() -> str:
        try:
            payload = api_market_refresh()
        except HTTPException as exc:
            return (
                f'<div class="warn">Refresh failed ({exc.status_code}): '
                f"{html.escape(str(exc.detail))}</div>"
            )
        errors = payload.get("errors", [])
        body = (
            f'<div class="ok">Refreshed <b>{payload["item_count"]}</b> items from '
            f'{", ".join(payload["sources"]) or "no sources"} '
            f"at {payload['generated_at']}.</div>"
        )
        if errors:
            body += (
                '<div class="warn">Partial failures:<ul>'
                + "".join(f"<li>{html.escape(e)}</li>" for e in errors)
                + "</ul></div>"
            )
        return body

    @app.post(
        "/api/recommend",
        response_model=RecommendResponse,
        dependencies=[Depends(_require_token)],
    )
    def api_recommend(req: RecommendRequest) -> RecommendResponse:
        snap = _load_snapshot()
        items, _deals = _load_market()
        constraint = BudgetConstraint(
            max_usd=req.budget_usd,
            socket=req.socket,
            ram_type=req.ram_type,
            target_workload=req.workload,
        )
        plan = _pick_optimizer(req.strategy)(snap, constraint, items)
        by_id = {c.id: c for c in snap.components}
        return RecommendResponse(
            strategy=plan.strategy,
            total_usd=plan.total_usd,
            overall_perf_uplift_pct=plan.overall_perf_uplift_pct,
            items=[
                _build_upgrade_item_dto(it, by_id.get(it.replaces_component_id or ""))
                for it in plan.items
            ],
        )

    @app.post(
        "/api/quote",
        response_class=JSONResponse,
        dependencies=[Depends(_require_token)],
    )
    def api_quote(
        req: RecommendRequest,
        zip_code: str | None = None,
    ) -> dict[str, Any]:
        snap = _load_snapshot()
        items, deals = _load_market()
        constraint = BudgetConstraint(
            max_usd=req.budget_usd,
            socket=req.socket,
            ram_type=req.ram_type,
            target_workload=req.workload,
        )
        plan = _pick_optimizer(req.strategy)(snap, constraint, items)
        matching = tuple(
            d for d in deals if d.market_item_sku in {it.market_item.sku for it in plan.items}
        )
        quote = build_quote(plan, deals=matching, zip_code=zip_code)
        return json.loads(quote.model_dump_json())

    # -----------------------------------------------------------------
    # HTMX partials
    # -----------------------------------------------------------------

    @app.post(
        "/htmx/detect",
        response_class=HTMLResponse,
        dependencies=[Depends(_require_token)],
    )
    def htmx_detect() -> str:
        try:
            probe = detect_probe()
            snap = probe.collect()
        except Exception as exc:
            return (
                f'<div class="pill-row" style="margin-bottom:.6rem">'
                f'<span class="pill warn">detection failed: {html.escape(str(exc))}</span>'
                f"</div>"
            )
        app.state.detected_snapshot = snap
        return htmx_inventory()

    @app.get(
        "/htmx/inventory",
        response_class=HTMLResponse,
        dependencies=[Depends(_require_token)],
    )
    def htmx_inventory() -> str:
        snap = _load_snapshot()
        deprecations = evaluate_all(snap)
        rows = "\n".join(
            "<tr>"
            f"<td><span class='pill kind-pill'>{html.escape(c.kind.value)}</span></td>"
            f"<td>{html.escape(c.vendor)}</td>"
            f"<td>{html.escape(c.model)}</td>"
            f"<td>{_render_specs_list(c.specs)}</td>"
            "</tr>"
            for c in snap.components
        )
        pills = "".join(
            f'<span class="pill warn">{html.escape(w)}</span>' for w in deprecations
        ) or '<span class="pill">no deprecations</span>'
        return (
            f'<div class="pill-row" style="margin-bottom:.6rem">{pills}</div>'
            f'<table><thead><tr>'
            f'<th>Kind</th><th>Vendor</th><th>Model</th><th>Specs</th>'
            f'</tr></thead><tbody>{rows}</tbody></table>'
        )

    @app.get(
        "/htmx/plan",
        response_class=HTMLResponse,
        dependencies=[Depends(_require_token)],
    )
    def htmx_plan(
        budget: float,
        workload: str = "gaming_1440p",
        strategy: str = "greedy",
    ) -> str:
        req = RecommendRequest(
            budget_usd=Decimal(str(budget)),
            workload=Workload(workload),
            strategy=strategy,
        )
        resp = api_recommend(req)
        return _render_plan_fragment(resp, quote=None)

    @app.get(
        "/htmx/quote",
        response_class=HTMLResponse,
        dependencies=[Depends(_require_token)],
    )
    def htmx_quote(
        budget: float,
        workload: str = "gaming_1440p",
        strategy: str = "greedy",
        zip: str | None = None,  # noqa: A002 - intentional HTMX param name
    ) -> str:
        req = RecommendRequest(
            budget_usd=Decimal(str(budget)),
            workload=Workload(workload),
            strategy=strategy,
        )
        plan_resp = api_recommend(req)
        # Build a real Quote to get tax/shipping numbers.
        snap = _load_snapshot()
        items, deals = _load_market()
        constraint = BudgetConstraint(
            max_usd=req.budget_usd,
            socket=req.socket,
            ram_type=req.ram_type,
            target_workload=req.workload,
        )
        plan = _pick_optimizer(req.strategy)(snap, constraint, items)
        matching = tuple(
            d for d in deals if d.market_item_sku in {it.market_item.sku for it in plan.items}
        )
        quote = build_quote(plan, deals=matching, zip_code=zip)
        totals = {
            "subtotal": f"${quote.plan.total_usd:.2f}",
            "tax": f"${quote.tax_usd:.2f}",
            "shipping": f"${quote.shipping_usd:.2f}",
            "grand": f"${quote.grand_total_usd:.2f}",
        }
        return _render_plan_fragment(plan_resp, quote=totals)

    return app


# ---------------------------------------------------------------------------
# HTML fragment helpers (kept small; real templating lives in the dashboard)
# ---------------------------------------------------------------------------


def _build_upgrade_item_dto(
    item: Any, current: Any | None
) -> UpgradeItemDTO:
    """Build the enriched DTO. ``current`` is the Component being replaced (or None)."""

    return UpgradeItemDTO(
        kind=item.kind,
        vendor=item.market_item.vendor,
        model=item.market_item.model,
        price_usd=item.market_item.price_usd,
        perf_uplift_pct=item.perf_uplift_pct,
        rationale=item.rationale,
        url=item.market_item.url,
        source=item.market_item.source,
        current_vendor=current.vendor if current is not None else None,
        current_model=current.model if current is not None else None,
        current_specs=dict(current.specs) if current is not None else {},
        new_specs=dict(item.market_item.specs),
    )


def _render_specs_list(specs: dict[str, Any]) -> str:
    """Render a component's specs as a falling (vertical) bullet list."""

    if not specs:
        return '<span class="muted">no specs on record</span>'
    items = "".join(
        f'<li><span class="spec-k">{html.escape(_spec_label(k))}</span>'
        f'<span class="spec-v">{html.escape(_fmt_spec_value(v))}</span></li>'
        for k, v in specs.items()
    )
    return f'<ul class="spec-list">{items}</ul>'


def _render_spec_diff(
    current: dict[str, Any], new: dict[str, Any]
) -> str:
    """Render an 'Improved specs' bullet list. Highlights changed / added keys."""

    if not new:
        return ""
    keys = list(new.keys())
    rows: list[str] = []
    for k in keys:
        new_val = _fmt_spec_value(new[k])
        if k in current:
            cur_val = _fmt_spec_value(current[k])
            if cur_val == new_val:
                rows.append(
                    f'<li class="spec-same">'
                    f'<span class="spec-k">{html.escape(_spec_label(k))}</span>'
                    f'<span class="spec-v">{html.escape(new_val)}</span>'
                    f'<span class="spec-tag">unchanged</span>'
                    f'</li>'
                )
            else:
                rows.append(
                    f'<li class="spec-change">'
                    f'<span class="spec-k">{html.escape(_spec_label(k))}</span>'
                    f'<span class="spec-v">'
                    f'<span class="spec-from">{html.escape(cur_val)}</span>'
                    f' <span class="spec-arrow">&rarr;</span> '
                    f'<span class="spec-to">{html.escape(new_val)}</span>'
                    f'</span>'
                    f'</li>'
                )
        else:
            rows.append(
                f'<li class="spec-new">'
                f'<span class="spec-k">{html.escape(_spec_label(k))}</span>'
                f'<span class="spec-v">{html.escape(new_val)}</span>'
                f'<span class="spec-tag">new</span>'
                f'</li>'
            )
    return f'<ul class="spec-diff">{"".join(rows)}</ul>'


def _render_plan_fragment(
    resp: RecommendResponse, *, quote: dict[str, str] | None
) -> str:
    if not resp.items:
        return '<p class="muted">No upgrade candidates fit the constraints.</p>'

    row_chunks: list[str] = []
    for it in resp.items:
        uplift_cls = "uplift-pos" if it.perf_uplift_pct > 0 else "uplift-zero"
        replaces = ""
        if it.current_vendor or it.current_model:
            replaces = (
                '<div class="replaces">replaces '
                f'<b>{html.escape((it.current_vendor or "").strip())} '
                f'{html.escape((it.current_model or "").strip())}</b></div>'
            )
        safe_url = _safe_external_url(it.url)
        if safe_url is not None:
            model_html = (
                f'<a class="upgrade-link" href="{html.escape(safe_url, quote=True)}" '
                f'target="_blank" rel="noopener noreferrer" '
                f'title="Open product page ({html.escape(safe_url, quote=True)})">'
                f'{html.escape(it.model)}'
                f'<span class="external-icon" aria-hidden="true">&nearr;</span>'
                '</a>'
            )
        else:
            model_html = html.escape(it.model)
        source_badge = (
            f'<span class="pill source-pill" title="Source: {html.escape(it.source)}">'
            f'{html.escape(it.source)}</span>'
            if it.source
            else ""
        )
        detail_blocks: list[str] = []
        diff_html = _render_spec_diff(it.current_specs, it.new_specs)
        if diff_html:
            detail_blocks.append(
                '<div class="detail-block">'
                '<div class="detail-title">Improved specs</div>'
                f'{diff_html}'
                '</div>'
            )
        if it.rationale:
            detail_blocks.append(
                '<div class="detail-block">'
                '<div class="detail-title">Rationale</div>'
                f'<p class="rationale">{html.escape(it.rationale)}</p>'
                '</div>'
            )
        detail_html = (
            f'<tr class="plan-detail"><td colspan="4">'
            f'<div class="detail-grid">{"".join(detail_blocks)}</div>'
            f'</td></tr>'
            if detail_blocks
            else ""
        )
        row_chunks.append(
            '<tr class="plan-row">'
            f'<td><span class="pill kind-pill">{html.escape(it.kind.value)}</span></td>'
            '<td>'
            f'<div class="upgrade-to"><b>{html.escape(it.vendor)}</b> {model_html} {source_badge}</div>'
            f'{replaces}'
            '</td>'
            f'<td class="num">${it.price_usd:.2f}</td>'
            f'<td class="num {uplift_cls}">+{it.perf_uplift_pct:.1f}%</td>'
            '</tr>'
            + detail_html
        )
    rows = "\n".join(row_chunks)

    if quote:
        totals_html = (
            '<div class="totals">'
            f'<div class="tile"><div class="k">Subtotal</div><div class="v">{quote["subtotal"]}</div></div>'
            f'<div class="tile"><div class="k">Tax</div><div class="v">{quote["tax"]}</div></div>'
            f'<div class="tile"><div class="k">Shipping</div><div class="v">{quote["shipping"]}</div></div>'
            f'<div class="tile"><div class="k">Grand total</div><div class="v">{quote["grand"]}</div></div>'
            '</div>'
        )
    else:
        totals_html = (
            '<div class="totals">'
            f'<div class="tile"><div class="k">Strategy</div><div class="v">{html.escape(resp.strategy)}</div></div>'
            f'<div class="tile"><div class="k">Plan total</div><div class="v">${resp.total_usd:.2f}</div></div>'
            f'<div class="tile"><div class="k">Overall uplift</div><div class="v">+{resp.overall_perf_uplift_pct:.1f}%</div></div>'
            '</div>'
        )
    return (
        '<section class="plan">'
        '<table class="plan-table"><thead><tr>'
        '<th>Kind</th><th>Upgrade</th><th>Price</th><th>Uplift</th>'
        '</tr></thead>'
        f'<tbody>{rows}</tbody></table>'
        f'{totals_html}'
        '</section>'
    )
