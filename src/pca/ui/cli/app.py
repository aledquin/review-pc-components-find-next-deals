"""Wave 1 CLI. Six subcommands wire the orchestrator together."""

from __future__ import annotations

import json
import platform
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

from pca.budget.optimizer_greedy import optimize_greedy
from pca.budget.optimizer_ilp import optimize_ilp
from pca.budget.optimizer_multi import optimize_multi
from pca.core.config import get_settings
from pca.core.errors import InventoryError
from pca.core.models import (
    BudgetConstraint,
    ComponentKind,
    Deal,
    MarketItem,
    SystemSnapshot,
    Workload,
)
from pca.deprecation.rules import evaluate_all
from pca.inventory.probe import detect_probe
from pca.quoting.builder import build_quote
from pca.reporting.builder import write_quote, write_report

app = typer.Typer(
    name="pca",
    help="PC Upgrade Advisor - inventory, benchmark, compare, and upgrade within budget.",
    no_args_is_help=True,
    add_completion=False,
)
console = Console()

# -------- helpers --------


def _load_stub_snapshot(path: Path) -> SystemSnapshot:
    return SystemSnapshot.model_validate_json(path.read_text(encoding="utf-8"))


def _load_market(path: Path) -> tuple[tuple[MarketItem, ...], tuple[Deal, ...]]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    items = tuple(MarketItem.model_validate(i) for i in raw.get("items", []))
    deals = tuple(Deal.model_validate(d) for d in raw.get("deals", []))
    return items, deals


def _socket(snap: SystemSnapshot) -> str | None:
    for kind in (ComponentKind.MOTHERBOARD, ComponentKind.CPU):
        for c in snap.components_of(kind):
            sk = c.specs.get("socket")
            if isinstance(sk, str):
                return sk
    return None


def _ram_type(snap: SystemSnapshot) -> str | None:
    for c in snap.components_of(ComponentKind.RAM):
        rt = c.specs.get("type")
        if isinstance(rt, str):
            return rt
    return None


def _resolve_snapshot(stub_path: Path | None) -> SystemSnapshot:
    if stub_path is not None:
        return _load_stub_snapshot(stub_path)
    if platform.system() != "Windows":
        console.print(
            "[red]Live inventory is Windows-only in the MVP. "
            "Pass --stub path/to/rig.json to use a fixture.[/]"
        )
        raise typer.Exit(code=2)
    try:
        return detect_probe().collect()
    except InventoryError as exc:  # pragma: no cover - env-specific
        console.print(f"[red]{exc}[/]")
        raise typer.Exit(code=2) from exc


def _dispatch_optimizer(
    strategy: str,
    snap: SystemSnapshot,
    constraint: BudgetConstraint,
    items: tuple[MarketItem, ...],
):
    if strategy == "ilp":
        return optimize_ilp(snap, constraint, items)
    if strategy == "multi":
        return optimize_multi(snap, constraint, items)
    return optimize_greedy(snap, constraint, items)


# -------- commands --------


@app.command()
def inventory(
    stub: Annotated[
        Path | None,
        typer.Option("--stub", help="Load a SystemSnapshot JSON instead of live probe."),
    ] = None,
    out: Annotated[
        Path | None, typer.Option("--out", help="Write snapshot JSON here.")
    ] = None,
) -> None:
    """Detect the installed hardware and print a summary table."""
    snap = _resolve_snapshot(stub)
    table = Table(title=f"Inventory - {snap.id}", show_lines=False)
    for col in ("Kind", "Vendor", "Model", "Specs"):
        table.add_column(col)
    for comp in snap.components:
        table.add_row(
            comp.kind.value,
            comp.vendor,
            comp.model,
            ", ".join(f"{k}={v}" for k, v in comp.specs.items()),
        )
    console.print(table)
    if out is not None:
        out.write_text(snap.model_dump_json(indent=2), encoding="utf-8")
        console.print(f"[green]wrote[/] {out}")


@app.command()
def report(
    stub: Annotated[Path | None, typer.Option("--stub")] = None,
    out_dir: Annotated[
        Path | None, typer.Option("--out-dir", help="Defaults to PCA report dir.")
    ] = None,
) -> None:
    """Generate a HTML + JSON report for the current (or stubbed) rig."""
    snap = _resolve_snapshot(stub)
    target = out_dir or get_settings().resolved_report_dir()
    deprecations = evaluate_all(snap)
    r = write_report(snap, target, deprecations=deprecations)
    console.print(f"[green]report[/] {r.html_path}")
    console.print(f"[green]json  [/] {r.json_path}")
    if deprecations:
        console.print("[yellow]deprecation warnings:[/]")
        for w in deprecations:
            console.print(f"  - {w}")


@app.command()
def market(
    market_file: Annotated[
        Path,
        typer.Option(
            "--market", help="Path to a market snapshot JSON fixture (MVP stand-in)."
        ),
    ],
) -> None:
    """Summarize a cached market snapshot. Live API calls land in Wave 1.x."""
    items, deals = _load_market(market_file)
    table = Table(title=f"Market snapshot ({len(items)} items, {len(deals)} deals)")
    for col in ("Kind", "SKU", "Model", "Price", "Source"):
        table.add_column(col)
    for item in sorted(items, key=lambda i: (i.kind.value, i.sku)):
        table.add_row(
            item.kind.value,
            item.sku,
            item.model,
            f"${item.price_usd:.2f}",
            item.source,
        )
    console.print(table)


@app.command()
def recommend(
    budget: Annotated[
        float, typer.Option("--budget", help="USD budget cap.", min=1.0)
    ],
    market_file: Annotated[Path, typer.Option("--market")],
    stub: Annotated[Path | None, typer.Option("--stub")] = None,
    strategy: Annotated[str, typer.Option("--strategy")] = "greedy",
    workload: Annotated[str, typer.Option("--workload")] = "gaming_1440p",
) -> None:
    """Compute an ``UpgradePlan`` for the given budget + rig + market."""
    snap = _resolve_snapshot(stub)
    items, _ = _load_market(market_file)
    constraint = BudgetConstraint(
        max_usd=Decimal(str(budget)),
        socket=_socket(snap),
        ram_type=_ram_type(snap),
        target_workload=Workload(workload),
    )
    plan = _dispatch_optimizer(strategy, snap, constraint, items)
    table = Table(title=f"Upgrade plan ({plan.strategy}, ${plan.total_usd})")
    for col in ("Kind", "Vendor", "Model", "Price", "+%", "Rationale"):
        table.add_column(col)
    for it in plan.items:
        table.add_row(
            it.kind.value,
            it.market_item.vendor,
            it.market_item.model,
            f"${it.market_item.price_usd:.2f}",
            f"{it.perf_uplift_pct:.1f}",
            it.rationale,
        )
    console.print(table)
    console.print(
        f"[bold]overall uplift[/]: {plan.overall_perf_uplift_pct:.1f}% "
        f"(workload: {workload})"
    )


@app.command()
def quote(
    budget: Annotated[float, typer.Option("--budget", min=1.0)],
    market_file: Annotated[Path, typer.Option("--market")],
    stub: Annotated[Path | None, typer.Option("--stub")] = None,
    zip_code: Annotated[str | None, typer.Option("--zip", help="US ZIP for tax estimate.")] = None,
    out_dir: Annotated[Path | None, typer.Option("--out-dir")] = None,
    strategy: Annotated[str, typer.Option("--strategy")] = "greedy",
) -> None:
    """End-to-end pipeline: recommend -> build Quote -> write HTML + JSON."""
    snap = _resolve_snapshot(stub)
    items, deals = _load_market(market_file)
    constraint = BudgetConstraint(
        max_usd=Decimal(str(budget)),
        socket=_socket(snap),
        ram_type=_ram_type(snap),
    )
    plan = _dispatch_optimizer(strategy, snap, constraint, items)
    matching_deals = tuple(
        d for d in deals if d.market_item_sku in {it.market_item.sku for it in plan.items}
    )
    q = build_quote(
        plan,
        deals=matching_deals,
        zip_code=zip_code,
        generated_at=datetime.now(UTC),
    )
    target = out_dir or get_settings().resolved_report_dir()
    name = f"quote-{snap.id}-{int(budget)}"
    out = write_quote(q, target, name=name)
    console.print(f"[green]html[/] {out['html_path']}")
    console.print(f"[green]json[/] {out['json_path']}")
    console.print(
        f"[bold]grand total[/] ${q.grand_total_usd:.2f} "
        f"(subtotal ${q.plan.total_usd:.2f}, tax ${q.tax_usd:.2f}, shipping ${q.shipping_usd:.2f})"
    )


@app.command()
def serve(
    stub: Annotated[Path | None, typer.Option("--stub")] = None,
    market_file: Annotated[
        Path | None,
        typer.Option("--market", help="Market snapshot fixture consumed by the dashboard."),
    ] = None,
    host: Annotated[str, typer.Option("--host")] = "127.0.0.1",
    port: Annotated[int, typer.Option("--port", min=1, max=65535)] = 8765,
    lan_token: Annotated[
        str | None,
        typer.Option(
            "--token",
            help="Required when binding to a non-loopback address.",
        ),
    ] = None,
) -> None:
    """Wave 3: launch the local FastAPI + HTMX dashboard."""
    try:
        import uvicorn
    except ImportError as exc:  # pragma: no cover
        console.print(
            "[red]FastAPI + uvicorn not installed. "
            "Install the 'web' extra: pip install pc-upgrade-advisor[web][/]"
        )
        raise typer.Exit(code=2) from exc

    if host not in {"127.0.0.1", "::1", "localhost"} and not lan_token:
        console.print("[red]non-loopback host requires --token <secret>[/]")
        raise typer.Exit(code=2)

    from pca.ui.web.app import ServerConfig, create_app

    cfg = ServerConfig(
        snapshot_path=stub,
        market_path=market_file,
        lan_token=lan_token,
    )
    fastapi_app = create_app(cfg)
    console.print(f"[green]serving[/] http://{host}:{port}  (Ctrl-C to stop)")
    uvicorn.run(fastapi_app, host=host, port=port, log_level="info")


@app.command()
def bench(
    stub: Annotated[Path | None, typer.Option("--stub")] = None,
    quick: Annotated[bool, typer.Option("--quick/--full")] = True,
) -> None:
    """Run a tiny built-in CPU benchmark. Real wrappers plug in later."""
    del stub  # bench does not need an inventory snapshot in MVP
    from pca.benchmarking.runner import BenchmarkRunner
    from pca.benchmarking.wrappers.cpu_builtin import BuiltinCpuWrapper

    wrapper = BuiltinCpuWrapper(iterations=500_000 if quick else 2_000_000)
    runner = BenchmarkRunner(passes=3, warmup=1, max_cv_pct=50.0)
    result = runner.run(wrapper, component_id="cpu-host")
    console.print(
        f"{result.metric}: median={result.median:.0f} {result.unit} "
        f"(MAD={result.mad:.0f}, CV={result.cv_pct:.2f}%)"
    )


def main() -> None:  # pragma: no cover - trivial
    app()
