"""Functional tests for the Wave 1 CLI.

The golden check is intentionally minimal: we verify that the CLI exits 0 for
happy-path fixtures, writes the expected artifacts, and prints the key totals.
Snapshot/golden-file comparisons of the HTML live in ``test_expected_reports``.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from pca.ui.cli.app import app
from tests.fixtures import INV_DIR, MARKET_DIR


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


def test_help_lists_all_subcommands(runner: CliRunner) -> None:
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0, result.output
    for sub in ("inventory", "report", "market", "recommend", "quote", "bench"):
        assert sub in result.output


def test_inventory_stub_prints_table(runner: CliRunner) -> None:
    result = runner.invoke(app, ["inventory", "--stub", str(INV_DIR / "rig_mid.json")])
    assert result.exit_code == 0, result.output
    assert "Inventory" in result.output


def test_inventory_stub_writes_json(runner: CliRunner, tmp_path: Path) -> None:
    out = tmp_path / "snap.json"
    result = runner.invoke(
        app,
        [
            "inventory",
            "--stub",
            str(INV_DIR / "rig_budget.json"),
            "--out",
            str(out),
        ],
    )
    assert result.exit_code == 0, result.output
    assert out.exists()
    raw = json.loads(out.read_text(encoding="utf-8"))
    assert raw["id"] == "rig_budget"


def test_market_prints_item_count(runner: CliRunner) -> None:
    result = runner.invoke(
        app,
        ["market", "--market", str(MARKET_DIR / "snapshot_normal.json")],
    )
    assert result.exit_code == 0, result.output
    assert "Market snapshot" in result.output


def test_recommend_produces_plan(runner: CliRunner) -> None:
    result = runner.invoke(
        app,
        [
            "recommend",
            "--stub",
            str(INV_DIR / "rig_budget.json"),
            "--market",
            str(MARKET_DIR / "snapshot_normal.json"),
            "--budget",
            "800",
        ],
    )
    assert result.exit_code == 0, result.output
    assert "Upgrade plan" in result.output
    assert "overall uplift" in result.output


def test_quote_writes_html_and_json(runner: CliRunner, tmp_path: Path) -> None:
    result = runner.invoke(
        app,
        [
            "quote",
            "--stub",
            str(INV_DIR / "rig_mid.json"),
            "--market",
            str(MARKET_DIR / "snapshot_normal.json"),
            "--budget",
            "1200",
            "--out-dir",
            str(tmp_path),
            "--zip",
            "10001",
        ],
    )
    assert result.exit_code == 0, result.output
    written = {p.suffix for p in tmp_path.iterdir()}
    assert ".html" in written
    assert ".json" in written
    assert "grand total" in result.output


def test_bench_quick(runner: CliRunner) -> None:
    result = runner.invoke(app, ["bench", "--quick"])
    assert result.exit_code == 0, result.output
    assert "median=" in result.output
