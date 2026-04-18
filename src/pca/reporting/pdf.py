"""PDF rendering via WeasyPrint.

WeasyPrint is an optional dependency (``reporting`` extra). On systems without
the native GTK/Pango/Cairo stack, we skip PDF generation rather than crash the
CLI - callers get ``None`` back and can continue with HTML + JSON only.

We explicitly do **not** byte-compare PDFs in golden tests. Font subsetting is
non-deterministic; instead we assert that the PDF is valid (starts with
``%PDF-``), parses back to the expected page count, and optionally pixel-diffs
a rendered page via ``pypdfium2`` when available (deferred until v1.x).
"""

from __future__ import annotations

import logging
from pathlib import Path

_LOG = logging.getLogger(__name__)


class PdfUnavailableError(RuntimeError):
    """Raised when WeasyPrint (or its native deps) can't be loaded."""


def _load_weasyprint() -> object | None:
    try:
        import weasyprint  # type: ignore[import-not-found]
    except Exception as exc:  # pragma: no cover - env-specific
        _LOG.info("weasyprint unavailable: %s", exc)
        return None
    return weasyprint


def pdf_available() -> bool:
    """Return True when WeasyPrint can be imported on the current host."""
    return _load_weasyprint() is not None


def render_html_to_pdf(
    html: str, out_path: Path, *, base_url: Path | None = None
) -> Path:
    """Render ``html`` to a PDF file. Raises PdfUnavailableError if we can't."""
    wp = _load_weasyprint()
    if wp is None:
        raise PdfUnavailableError(
            "weasyprint is not installed. Install the 'reporting' extra: "
            "pip install pc-upgrade-advisor[reporting]"
        )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    html_doc = wp.HTML(string=html, base_url=str(base_url) if base_url else None)  # type: ignore[attr-defined]
    html_doc.write_pdf(str(out_path))
    return out_path


def try_render_html_to_pdf(html: str, out_path: Path) -> Path | None:
    """Best-effort PDF rendering that degrades silently to None."""
    try:
        return render_html_to_pdf(html, out_path)
    except PdfUnavailableError:
        return None
    except Exception as exc:  # pragma: no cover - env-specific
        _LOG.warning("pdf render failed for %s: %s", out_path, exc)
        return None
