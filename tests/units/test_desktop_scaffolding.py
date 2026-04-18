"""Sanity-check the Wave 4 desktop scaffolding. We don't compile Rust in CI yet,
but we do pin the config shape so future refactors break loudly."""

from __future__ import annotations

import json
from pathlib import Path

import pytest


@pytest.fixture
def desktop_root() -> Path:
    root = Path(__file__).resolve().parents[2] / "desktop"
    if not root.exists():
        pytest.skip("desktop/ scaffolding not present (optional Wave 4 artifact)")
    return root


def test_tauri_config_exists_and_is_valid_json(desktop_root: Path) -> None:
    cfg = desktop_root / "src-tauri" / "tauri.conf.json"
    assert cfg.exists(), cfg
    data = json.loads(cfg.read_text(encoding="utf-8"))
    assert data["productName"] == "PC Upgrade Advisor"
    assert data["identifier"].startswith("com.pcupgradeadvisor")
    assert "sidecar" in json.dumps(data).lower() or "externalBin" in data.get("bundle", {})


def test_sidecar_is_declared(desktop_root: Path) -> None:
    cfg = desktop_root / "src-tauri" / "tauri.conf.json"
    data = json.loads(cfg.read_text(encoding="utf-8"))
    external = data["bundle"].get("externalBin", [])
    assert any("pca-sidecar" in b for b in external)


def test_cargo_toml_references_tauri_2(desktop_root: Path) -> None:
    cargo = (desktop_root / "src-tauri" / "Cargo.toml").read_text(encoding="utf-8")
    assert "tauri = " in cargo
    assert 'version = "2"' in cargo or 'version = "2' in cargo


def test_main_rs_loads_sidecar(desktop_root: Path) -> None:
    src = (desktop_root / "src-tauri" / "src" / "main.rs").read_text(encoding="utf-8")
    assert "pca-sidecar" in src
    assert "__PCA_TOKEN" in src
