"""Unit tests for the macOS inventory probe. Runner is injected."""

from __future__ import annotations

from pca.core.models import ComponentKind
from pca.inventory.macos import MacosInventoryProbe
from tests.fixtures import INV_DIR


def _runner_from(json_blob: str) -> callable:  # type: ignore[valid-type]
    def runner(argv: list[str]) -> str:
        if argv[0] == "system_profiler":
            return json_blob
        if argv == ["uname", "-m"]:
            return "arm64\n"
        if argv[:2] == ["sysctl", "-n"]:
            return "Apple M2 Pro\n"
        return ""

    return runner


def test_collect_returns_cpu_gpu_ram_storage_os() -> None:
    blob = (INV_DIR / "system_profiler_sample.json").read_text(encoding="utf-8")
    probe = MacosInventoryProbe(runner=_runner_from(blob))
    snap = probe.collect()
    kinds = {c.kind for c in snap.components}
    for kind in (
        ComponentKind.CPU,
        ComponentKind.GPU,
        ComponentKind.RAM,
        ComponentKind.STORAGE,
        ComponentKind.OS,
    ):
        assert kind in kinds


def test_apple_silicon_is_detected() -> None:
    blob = (INV_DIR / "system_profiler_sample.json").read_text(encoding="utf-8")
    probe = MacosInventoryProbe(runner=_runner_from(blob))
    snap = probe.collect()
    cpu = snap.components_of(ComponentKind.CPU)[0]
    assert cpu.vendor == "Apple"
    assert "M2 Pro" in cpu.model


def test_os_info_parses_version_and_build() -> None:
    blob = (INV_DIR / "system_profiler_sample.json").read_text(encoding="utf-8")
    probe = MacosInventoryProbe(runner=_runner_from(blob))
    snap = probe.collect()
    assert snap.os_info.family == "macOS"
    assert snap.os_info.version == "14.4.1"
    assert snap.os_info.build == "23E224"
    assert snap.os_info.arch == "arm64"


def test_sysctl_fallback_produces_cpu_component() -> None:
    # Even without system_profiler output, the sysctl fallback supplies a CPU.
    probe = MacosInventoryProbe(runner=_runner_from(""))
    snap = probe.collect()
    cpus = snap.components_of(ComponentKind.CPU)
    assert cpus and "M2 Pro" in cpus[0].model


def test_empty_runner_still_produces_os_only_snapshot() -> None:
    # If neither system_profiler nor sysctl return anything, we still emit a
    # snapshot with just the OS row (marked "unknown"). This is intentional
    # per the macOS probe's informational-only posture.
    def silent(argv: list[str]) -> str:
        return ""

    snap = MacosInventoryProbe(runner=silent).collect()
    kinds = {c.kind for c in snap.components}
    assert kinds == {ComponentKind.OS}
