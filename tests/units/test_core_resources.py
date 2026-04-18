"""Resource-root resolver must work in dev, wheel, and PyInstaller modes."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from pca.core import resources as res


def test_resource_root_dev_install_points_at_repo_resources() -> None:
    root = res.resource_root()
    assert root.name == "resources"
    assert (root / "templates" / "report.html.j2").is_file()
    assert (root / "catalogs" / "us_tax_rates.yaml").is_file()


def test_resource_path_joins_under_root() -> None:
    p = res.resource_path("catalogs", "us_tax_rates.yaml")
    assert p.is_file()
    assert p.parent.name == "catalogs"


def test_frozen_mode_uses_meipass(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """When sys.frozen is set, resources live under sys._MEIPASS/resources."""
    bundle = tmp_path / "bundle"
    (bundle / "resources" / "templates").mkdir(parents=True)
    (bundle / "resources" / "templates" / "report.html.j2").write_text("x", encoding="utf-8")

    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(bundle), raising=False)
    res.resource_root.cache_clear()

    root = res.resource_root()
    assert root == bundle / "resources"
    assert (root / "templates" / "report.html.j2").is_file()

    res.resource_root.cache_clear()


def test_resource_root_is_cached() -> None:
    res.resource_root.cache_clear()
    a = res.resource_root()
    b = res.resource_root()
    assert a is b
