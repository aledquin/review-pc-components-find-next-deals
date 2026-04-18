"""Functional: report JSON output matches ``tests/data/expected_reports/``."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from pca.deprecation.rules import evaluate_all
from pca.reporting.builder import write_report
from tests.fixtures import REPORTS_DIR, RIG_IDS, load_rig


@pytest.mark.parametrize("rig_id", RIG_IDS)
def test_report_json_matches_golden(rig_id: str, tmp_path) -> None:
    rig = load_rig(rig_id)
    deprecations = evaluate_all(rig)
    report = write_report(rig, tmp_path, deprecations=deprecations)
    actual = json.loads(Path(report.json_path).read_text(encoding="utf-8"))

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    golden = REPORTS_DIR / f"{rig_id}.json"
    if not golden.exists():
        golden.write_text(json.dumps(actual, indent=2), encoding="utf-8")
        pytest.skip(f"Created missing golden: {golden}")

    expected = json.loads(golden.read_text(encoding="utf-8"))
    assert actual == expected
