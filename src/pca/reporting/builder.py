"""Report and quote HTML + JSON builders.

PDF is deferred to Wave 2 (WeasyPrint) per the plan.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, StrictUndefined, select_autoescape

from pca.core.models import Quote, Report, SystemSnapshot


def _templates_path() -> Path:
    # The repo layout places templates under ``resources/templates/`` at the
    # project root. ``parents[3]`` walks up from
    # ``src/pca/reporting/builder.py`` to the repo root.
    return Path(__file__).resolve().parents[3] / "resources" / "templates"


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
) -> str:
    template = _env().get_template("report.html.j2")
    return template.render(snapshot=snapshot, deprecations=deprecations or [])


def render_quote_html(quote: Quote) -> str:
    template = _env().get_template("quote.html.j2")
    return template.render(quote=quote)


def write_report(
    snapshot: SystemSnapshot,
    out_dir: Path,
    *,
    deprecations: list[str] | None = None,
) -> Report:
    """Write both HTML and JSON forms of the report. Returns the ``Report`` entity."""
    out_dir.mkdir(parents=True, exist_ok=True)
    html_path = out_dir / f"{snapshot.id}.html"
    json_path = out_dir / f"{snapshot.id}.json"

    html_path.write_text(
        render_report_html(snapshot, deprecations=deprecations),
        encoding="utf-8",
    )
    json_path.write_text(
        snapshot.model_dump_json(indent=2),
        encoding="utf-8",
    )
    return Report(
        snapshot_id=snapshot.id,
        html_path=str(html_path),
        pdf_path=None,
        json_path=str(json_path),
    )


def write_quote(quote: Quote, out_dir: Path, name: str) -> dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)
    html_path = out_dir / f"{name}.html"
    json_path = out_dir / f"{name}.json"

    html_path.write_text(render_quote_html(quote), encoding="utf-8")
    json_path.write_text(
        quote.model_dump_json(indent=2),
        encoding="utf-8",
    )
    return {
        "html_path": str(html_path),
        "json_path": str(json_path),
        "quote": json.loads(quote.model_dump_json()),
    }
