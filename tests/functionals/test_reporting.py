"""Functional: the reporting pipeline produces valid HTML and round-trippable JSON."""

from __future__ import annotations

from pathlib import Path

import pytest

from pca.reporting.builder import render_report_html, write_report
from tests.fixtures import RIG_IDS, load_rig


@pytest.mark.parametrize("rig_id", RIG_IDS)
def test_report_html_renders(rig_id: str) -> None:
    snap = load_rig(rig_id)
    html = render_report_html(snap, deprecations=["LGA1151 is end-of-life."])
    assert "<!doctype html>" in html.lower()
    assert snap.id in html
    for c in snap.components:
        assert c.model in html or c.model == "Unknown"


@pytest.mark.parametrize("rig_id", RIG_IDS)
def test_write_report_produces_both_files(rig_id: str, tmp_path: Path) -> None:
    snap = load_rig(rig_id)
    report = write_report(snap, tmp_path / "out")
    assert Path(report.html_path).exists()
    assert Path(report.json_path).exists()
    assert Path(report.html_path).read_text(encoding="utf-8").startswith("<!doctype")
    round_tripped = type(snap).model_validate_json(
        Path(report.json_path).read_text(encoding="utf-8")
    )
    assert round_tripped == snap
