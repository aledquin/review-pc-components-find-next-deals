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

import json
from decimal import Decimal
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
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
# Factory
# ---------------------------------------------------------------------------


def _pick_optimizer(strategy: str):
    if strategy == "ilp":
        return optimize_ilp
    if strategy == "multi":
        return optimize_multi
    return optimize_greedy


def create_app(config: ServerConfig | None = None) -> FastAPI:
    cfg = config or ServerConfig()
    app = FastAPI(
        title="PC Upgrade Advisor",
        version="0.3.0",
        docs_url="/api",
    )

    def _require_token(request: Request) -> None:
        # When a token is configured (LAN mode), every request must match.
        # Loopback callers bypass the gate so local CLI smoke tests still work.
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
        return _index_html(cfg.ui_disclaimer)

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
        rows = "\n".join(
            f'<tr><td>{it.kind.value}</td><td>{it.vendor}</td>'
            f'<td>{it.model}</td><td>${it.price_usd:.2f}</td>'
            f'<td>+{it.perf_uplift_pct:.1f}%</td></tr>'
            for it in resp.items
        )
        return (
            f'<section class="plan">'
            f'<h3>Plan ({resp.strategy}): total ${resp.total_usd:.2f} - '
            f'overall uplift {resp.overall_perf_uplift_pct:.1f}%</h3>'
            f'<table><thead><tr><th>Kind</th><th>Vendor</th><th>Model</th>'
            f'<th>Price</th><th>Uplift</th></tr></thead>'
            f'<tbody>{rows or "<tr><td colspan=5>no candidates</td></tr>"}</tbody>'
            f'</table></section>'
        )

    return app


# ---------------------------------------------------------------------------
# HTML shell
# ---------------------------------------------------------------------------


def _index_html(disclaimer: str) -> str:
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>PC Upgrade Advisor - dashboard</title>
  <script src="https://unpkg.com/htmx.org@1.9.12"></script>
  <script defer src="https://unpkg.com/alpinejs@3.13.5"></script>
  <style>
    body {{ font-family: -apple-system, Segoe UI, Roboto, sans-serif;
           max-width: 960px; margin: 2rem auto; padding: 0 1rem; }}
    h1 {{ border-bottom: 2px solid #333; padding-bottom: .3rem; }}
    table {{ border-collapse: collapse; width: 100%; margin: .5rem 0; }}
    th, td {{ border: 1px solid #ccc; padding: .3rem .6rem; text-align: left; }}
    th {{ background: #f3f3f3; }}
    .muted {{ color: #666; font-size: .9rem; }}
    input, select, button {{ font: inherit; padding: .3rem .5rem; }}
  </style>
</head>
<body x-data="{{ budget: 800, workload: 'gaming_1440p', strategy: 'greedy' }}">
  <h1>PC Upgrade Advisor</h1>
  <p class="muted">{disclaimer}</p>

  <section>
    <h2>Plan</h2>
    <form>
      <label>Budget $<input type="number" x-model.number="budget" min="100" step="50"></label>
      <label>Workload
        <select x-model="workload">
          <option value="gaming_1080p">1080p</option>
          <option value="gaming_1440p">1440p</option>
          <option value="gaming_4k">4K</option>
          <option value="productivity">productivity</option>
          <option value="content_creation">content creation</option>
          <option value="ml_workstation">ML workstation</option>
        </select>
      </label>
      <label>Strategy
        <select x-model="strategy">
          <option value="greedy">greedy</option>
          <option value="ilp">ilp</option>
          <option value="multi">multi (perf/power/noise)</option>
        </select>
      </label>
      <button type="button"
              hx-get="/htmx/plan"
              hx-target="#plan"
              :hx-vals="JSON.stringify({{budget:budget, workload:workload, strategy:strategy}})">
        Recommend
      </button>
    </form>
    <div id="plan"></div>
  </section>

  <section>
    <h2>Inventory</h2>
    <button hx-get="/api/inventory" hx-target="#inventory-json">Load</button>
    <pre id="inventory-json" class="muted"></pre>
  </section>
</body>
</html>"""
