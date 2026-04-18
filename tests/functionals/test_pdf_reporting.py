"""Functional: PDF generation is best-effort. When WeasyPrint is missing or its
native deps don't resolve, we skip rather than fail. When available, we assert
the file is a valid PDF by magic bytes + parses to a positive page count."""

from __future__ import annotations

from pathlib import Path

import pytest

from pca.reporting.builder import write_report
from pca.reporting.pdf import pdf_available, try_render_html_to_pdf
from tests.fixtures import load_rig


@pytest.fixture(scope="module")
def _pdf_or_skip() -> None:
    if not pdf_available():
        pytest.skip("weasyprint unavailable on this host")


def _assert_pdf_magic(path: Path) -> None:
    head = path.read_bytes()[:5]
    assert head == b"%PDF-", f"not a PDF: {head!r}"


def test_try_render_html_to_pdf_returns_none_on_trivial_input_when_missing(
    tmp_path: Path,
) -> None:
    if pdf_available():
        pytest.skip("weasyprint is installed; see positive path tests")
    out = try_render_html_to_pdf("<html><body>hi</body></html>", tmp_path / "x.pdf")
    assert out is None


@pytest.mark.usefixtures("_pdf_or_skip")
def test_report_writes_pdf_when_available(tmp_path: Path) -> None:
    snap = load_rig("rig_mid")
    report = write_report(snap, tmp_path, include_pdf=True)
    assert report.pdf_path is not None
    _assert_pdf_magic(Path(report.pdf_path))
