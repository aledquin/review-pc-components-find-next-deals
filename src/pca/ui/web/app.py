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
from pca.quoting.builder import build_quote


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
        if cfg.snapshot_path and cfg.snapshot_path.exists():
            return SystemSnapshot.model_validate_json(
                cfg.snapshot_path.read_text(encoding="utf-8")
            )
        raise HTTPException(status_code=404, detail="snapshot not configured")

    def _load_market() -> tuple[tuple[MarketItem, ...], tuple[Any, ...]]:
        from pca.core.models import Deal

        if cfg.market_path and cfg.market_path.exists():
            raw = json.loads(cfg.market_path.read_text(encoding="utf-8"))
            items = tuple(MarketItem.model_validate(i) for i in raw.get("items", []))
            deals = tuple(Deal.model_validate(d) for d in raw.get("deals", []))
            return items, deals
        raise HTTPException(status_code=404, detail="market not configured")

    # -----------------------------------------------------------------
    # Routes
    # -----------------------------------------------------------------

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/", response_class=HTMLResponse, dependencies=[Depends(_require_token)])
    def index() -> str:
        tmpl = _env().get_template("dashboard.html.j2")
        return tmpl.render(disclaimer=cfg.ui_disclaimer)

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
        return RecommendResponse(
            strategy=plan.strategy,
            total_usd=plan.total_usd,
            overall_perf_uplift_pct=plan.overall_perf_uplift_pct,
            items=[
                UpgradeItemDTO(
                    kind=it.kind,
                    vendor=it.market_item.vendor,
                    model=it.market_item.model,
                    price_usd=it.market_item.price_usd,
                    perf_uplift_pct=it.perf_uplift_pct,
                    rationale=it.rationale,
                )
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
            f"<td>{html.escape(c.kind.value)}</td>"
            f"<td>{html.escape(c.vendor)}</td>"
            f"<td>{html.escape(c.model)}</td>"
            f"<td class='muted'>{html.escape(_format_specs(c.specs))}</td>"
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


def _format_specs(specs: dict[str, Any]) -> str:
    parts = []
    for k, v in specs.items():
        parts.append(f"{k}={v}")
    return ", ".join(parts)


def _render_plan_fragment(
    resp: RecommendResponse, *, quote: dict[str, str] | None
) -> str:
    if not resp.items:
        return '<p class="muted">No upgrade candidates fit the constraints.</p>'

    rows = "\n".join(
        "<tr>"
        f"<td>{html.escape(it.kind.value)}</td>"
        f"<td>{html.escape(it.vendor)}</td>"
        f"<td>{html.escape(it.model)}</td>"
        f"<td class='num'>${it.price_usd:.2f}</td>"
        f"<td class='num'>+{it.perf_uplift_pct:.1f}%</td>"
        f"<td class='muted'>{html.escape(it.rationale)}</td>"
        "</tr>"
        for it in resp.items
    )
    totals_html = ""
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
        '<table><thead><tr>'
        '<th>Kind</th><th>Vendor</th><th>Model</th><th>Price</th>'
        '<th>Uplift</th><th>Rationale</th>'
        '</tr></thead>'
        f'<tbody>{rows}</tbody></table>'
        f'{totals_html}'
        '</section>'
    )
