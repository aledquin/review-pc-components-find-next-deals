"""Unit tests for the Linux inventory probe. Uses an injected runner + tmp_path
filesystem so it runs on any host (no real ``lshw``/``/proc`` access).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from pca.core.models import ComponentKind
from pca.inventory.linux import (
    LinuxInventoryProbe,
    _infer_ddr,
    _parse_os_release,
)
from tests.fixtures import INV_DIR


def _fake_runner_from(lshw_json: str) -> callable:  # type: ignore[valid-type]
    def runner(argv: list[str]) -> str:
        if argv[0] == "lshw":
            return lshw_json
        if argv == ["uname", "-m"]:
            return "x86_64\n"
        if argv == ["uname", "-r"]:
            return "6.6.8-arch1-1\n"
        return ""

    return runner


@pytest.fixture
def lshw_json() -> str:
    return (INV_DIR / "lshw_sample.json").read_text(encoding="utf-8")


@pytest.fixture
def os_release(tmp_path: Path) -> Path:
    p = tmp_path / "os-release"
    p.write_text(
        'NAME="Arch Linux"\nVERSION_ID="rolling"\nPRETTY_NAME="Arch Linux"\n',
        encoding="utf-8",
    )
    return p


def test_collect_parses_cpu_gpu_ram_storage(lshw_json: str, os_release: Path) -> None:
    probe = LinuxInventoryProbe(runner=_fake_runner_from(lshw_json), os_release=os_release)
    snap = probe.collect()
    kinds = {c.kind for c in snap.components}
    for k in (
        ComponentKind.CPU,
        ComponentKind.GPU,
        ComponentKind.RAM,
        ComponentKind.MOTHERBOARD,
        ComponentKind.STORAGE,
        ComponentKind.OS,
    ):
        assert k in kinds, f"missing {k}"


def test_cpu_fields_are_populated(lshw_json: str, os_release: Path) -> None:
    probe = LinuxInventoryProbe(runner=_fake_runner_from(lshw_json), os_release=os_release)
    snap = probe.collect()
    cpu = snap.components_of(ComponentKind.CPU)[0]
    assert cpu.vendor == "AMD"
    assert "Ryzen 5 3600" in cpu.model
    assert cpu.specs.get("cores") == 6
    assert cpu.specs.get("threads") == 12


def test_ram_infers_ddr_from_description(lshw_json: str, os_release: Path) -> None:
    probe = LinuxInventoryProbe(runner=_fake_runner_from(lshw_json), os_release=os_release)
    snap = probe.collect()
    ram = snap.components_of(ComponentKind.RAM)
    assert len(ram) == 2
    assert all(c.specs.get("type") == "DDR4" for c in ram)


def test_os_info_from_release(lshw_json: str, os_release: Path) -> None:
    probe = LinuxInventoryProbe(runner=_fake_runner_from(lshw_json), os_release=os_release)
    snap = probe.collect()
    assert snap.os_info.family == "Arch Linux"
    assert snap.os_info.arch == "x86_64"
    assert snap.os_info.build is not None


def test_fallback_to_proc_cpuinfo_when_lshw_missing(tmp_path: Path) -> None:
    proc = tmp_path / "cpuinfo"
    proc.write_text(
        "vendor_id\t: GenuineIntel\nmodel name\t: Intel(R) Core(TM) i5-8400 CPU @ 2.80GHz\n",
        encoding="utf-8",
    )
    os_release = tmp_path / "os-release"
    os_release.write_text('NAME="Ubuntu"\nVERSION_ID="22.04"\n', encoding="utf-8")
    mem = tmp_path / "meminfo"
    mem.write_text("MemTotal:       32768000 kB\n", encoding="utf-8")

    def empty(argv: list[str]) -> str:
        return ""

    probe = LinuxInventoryProbe(
        runner=empty,
        proc_cpuinfo=proc,
        meminfo=mem,
        os_release=os_release,
    )
    snap = probe.collect()
    cpu = snap.components_of(ComponentKind.CPU)[0]
    assert "i5-8400" in cpu.model
    ram = snap.components_of(ComponentKind.RAM)
    assert ram and ram[0].specs.get("capacity_gb") is not None


@pytest.mark.parametrize(
    ("desc", "expected"),
    [
        ("DIMM DDR4 Synchronous 3200 MHz", "DDR4"),
        ("SODIMM DDR5", "DDR5"),
        ("SDRAM", None),
        ("", None),
    ],
)
def test_infer_ddr(desc: str, expected: str | None) -> None:
    assert _infer_ddr(desc) == expected


def test_parse_os_release_handles_quoting() -> None:
    text = 'NAME="Arch"\nID=arch\nPRETTY_NAME="Arch Linux"\n# comment\n'
    got = _parse_os_release(text)
    assert got["NAME"] == "Arch"
    assert got["ID"] == "arch"
    assert got["PRETTY_NAME"] == "Arch Linux"
