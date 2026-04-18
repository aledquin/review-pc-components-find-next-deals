"""Unit tests for the deprecation catalog + rules."""

from __future__ import annotations

from datetime import date

from pca.deprecation.catalog import load_catalog
from pca.deprecation.rules import evaluate, evaluate_all, gpu_driver_warnings
from tests.fixtures import load_rig


def test_catalog_loads():
    cat = load_catalog()
    assert any(e.id == "LGA1151" for e in cat.sockets)
    assert any(e.id == "DDR3" for e in cat.memory_generations)
    assert cat.max_driver_age_days == 365


def test_budget_rig_flags_lga1151_socket():
    snap = load_rig("rig_budget")
    warnings = evaluate(snap, today=date(2025, 1, 1))
    joined = " | ".join(warnings)
    assert "LGA1151" in joined or "end-of-life" in joined.lower()


def test_mid_rig_is_clean_for_eol():
    snap = load_rig("rig_mid")
    warnings = evaluate(snap, today=date(2025, 1, 1))
    for w in warnings:
        assert "end-of-life" not in w.lower()


def test_highend_rig_has_no_warnings():
    snap = load_rig("rig_highend")
    assert evaluate_all(snap, today=date(2025, 1, 1)) == []


def test_gpu_driver_warnings_stub(monkeypatch):
    from pca.core.models import (
        Component,
        ComponentKind,
        OsInfo,
        SystemSnapshot,
    )
    from datetime import UTC, datetime

    snap = SystemSnapshot(
        id="s1",
        components=(
            Component(
                id="gpu-1",
                kind=ComponentKind.GPU,
                vendor="NVIDIA",
                model="GeForce RTX 2060",
                specs={"driver_date": "20220101000000.000000-420"},
            ),
        ),
        os_info=OsInfo(family="Windows", version="11"),
        captured_at=datetime(2025, 1, 1, tzinfo=UTC),
    )
    warnings = gpu_driver_warnings(snap, today=date(2025, 1, 1))
    assert len(warnings) == 1
    assert "driver" in warnings[0]
