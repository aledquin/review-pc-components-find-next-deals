"""Report and quote HTML + JSON + PDF builders."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, StrictUndefined, select_autoescape

from pca.core.models import Quote, Report, SystemSnapshot
from pca.core.resources import resource_path
from pca.reporting.charts import png_as_data_url, snapshot_scores_png
from pca.reporting.pdf import try_render_html_to_pdf


def _templates_path() -> Path:
    return resource_path("templates")


def _env() -> Environment:
    return Environment(
        loader=FileSystemLoader(str(_templates_path())),
        autoescape=select_autoescape(["html", "xml"]),
        undefined=StrictUndefined,
        trim_blocks=True,
        lstrip_blocks=True,
    )


def render_report_html(
    snapshot: SystemSnapshot,
    *,
    deprecations: list[str] | None = None,
    include_chart: bool = True,
) -> str:
    template = _env().get_template("report.html.j2")
    chart_data_url = ""
    if include_chart:
        try:
            chart_data_url = png_as_data_url(snapshot_scores_png(snapshot))
        except Exception:  # pragma: no cover - matplotlib misconfigured
            chart_data_url = ""
    return template.render(
        snapshot=snapshot,
        deprecations=deprecations or [],
        chart_data_url=chart_data_url,
    )


def render_quote_html(quote: Quote) -> str:
    template = _env().get_template("quote.html.j2")
    return template.render(quote=quote)


def write_report(
    snapshot: SystemSnapshot,
    out_dir: Path,
    *,
    deprecations: list[str] | None = None,
    include_pdf: bool = True,
) -> Report:
    """Write HTML, JSON (and best-effort PDF) forms of the report."""
    out_dir.mkdir(parents=True, exist_ok=True)
    html_path = out_dir / f"{snapshot.id}.html"
    json_path = out_dir / f"{snapshot.id}.json"

    html = render_report_html(snapshot, deprecations=deprecations)
    html_path.write_text(html, encoding="utf-8")
    json_path.write_text(
        snapshot.model_dump_json(indent=2),
        encoding="utf-8",
    )

    pdf_path: Path | None = None
    if include_pdf:
        pdf_path = try_render_html_to_pdf(html, out_dir / f"{snapshot.id}.pdf")

    return Report(
        snapshot_id=snapshot.id,
        html_path=str(html_path),
        pdf_path=str(pdf_path) if pdf_path else None,
        json_path=str(json_path),
    )


def write_quote(
    quote: Quote,
    out_dir: Path,
    name: str,
    *,
    include_pdf: bool = True,
) -> dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)
    html_path = out_dir / f"{name}.html"
    json_path = out_dir / f"{name}.json"

    html = render_quote_html(quote)
    html_path.write_text(html, encoding="utf-8")
    json_path.write_text(
        quote.model_dump_json(indent=2),
        encoding="utf-8",
    )

    pdf_path: Path | None = None
    if include_pdf:
        pdf_path = try_render_html_to_pdf(html, out_dir / f"{name}.pdf")

    return {
        "html_path": str(html_path),
        "json_path": str(json_path),
        "pdf_path": str(pdf_path) if pdf_path else None,
        "quote": json.loads(quote.model_dump_json()),
    }
