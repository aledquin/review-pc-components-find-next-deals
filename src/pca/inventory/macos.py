"""macOS inventory probe.

On Apple Silicon and recent Intel Macs most useful data comes from
``system_profiler -json``. We treat the output as the single source of
truth and fall back to ``sysctl`` for CPU detail when SPHardwareDataType
is unavailable. The probe reports components with the understanding that
per-component benchmarks on Apple Silicon don't align with PC references,
so benchmarks are flagged ``informational`` upstream.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from collections.abc import Callable
from typing import Any

from pca.core.errors import InventoryError
from pca.core.models import (
    Component,
    ComponentKind,
    OsInfo,
    SystemSnapshot,
)
from pca.inventory.normalize import normalize_model, normalize_vendor
from pca.inventory.probe import new_snapshot_id, now_utc

CommandRunner = Callable[[list[str]], str]


def _default_runner(argv: list[str]) -> str:
    exe = shutil.which(argv[0])
    if exe is None:
        return ""
    try:
        result = subprocess.run(  # noqa: S603 - argv is controlled
            [exe, *argv[1:]],
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )
    except (subprocess.TimeoutExpired, OSError):
        return ""
    return result.stdout or ""


_SP_DATATYPES = (
    "SPHardwareDataType",
    "SPMemoryDataType",
    "SPStorageDataType",
    "SPDisplaysDataType",
    "SPSoftwareDataType",
)


class MacosInventoryProbe:
    """macOS ``InventoryProbe`` implementation. Benchmarks are informational."""

    def __init__(self, *, runner: CommandRunner | None = None) -> None:
        self._run = runner or _default_runner

    def collect(self) -> SystemSnapshot:
        sp = self._system_profiler()
        components: list[Component] = []

        components.extend(self._cpu(sp))
        components.extend(self._gpu(sp))
        components.extend(self._ram(sp))
        components.extend(self._storage(sp))
        components.append(self._os_component(sp))

        if not components:
            raise InventoryError("macOS probe returned no components.")

        return SystemSnapshot(
            id=new_snapshot_id(),
            components=tuple(components),
            benchmarks=(),
            os_info=self._os_info(sp),
            captured_at=now_utc(),
        )

    # ------------------------------------------------------------------
    # system_profiler ingestion
    # ------------------------------------------------------------------

    def _system_profiler(self) -> dict[str, list[dict[str, Any]]]:
        raw = self._run(["system_profiler", "-json", *_SP_DATATYPES])
        if not raw:
            return {}
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return {}
        return data if isinstance(data, dict) else {}

    def _cpu(self, sp: dict[str, list[dict[str, Any]]]) -> list[Component]:
        hw = (sp.get("SPHardwareDataType") or [{}])[0]
        name = str(hw.get("chip_type") or hw.get("cpu_type") or "")
        if not name:
            name = (self._run(["sysctl", "-n", "machdep.cpu.brand_string"]) or "").strip()
        if not name:
            return []
        vendor = "Apple" if "Apple" in name else "Intel" if "Intel" in name else "Unknown"
        specs = {
            "cores": int(hw.get("number_processors", 0) or 0) or None,
        }
        return [
            Component(
                id="cpu-1",
                kind=ComponentKind.CPU,
                vendor=normalize_vendor(vendor),
                model=normalize_model(name),
                specs={k: v for k, v in specs.items() if v is not None},
            )
        ]

    def _gpu(self, sp: dict[str, list[dict[str, Any]]]) -> list[Component]:
        out: list[Component] = []
        for i, g in enumerate(sp.get("SPDisplaysDataType", []) or ()):
            model = str(g.get("sppci_model") or g.get("_name") or "")
            if not model:
                continue
            vendor = str(g.get("spdisplays_vendor") or "")
            if vendor.startswith("sppci_vendor_"):
                vendor = vendor.split("_")[-1].capitalize()
            out.append(
                Component(
                    id=f"gpu-{i + 1}",
                    kind=ComponentKind.GPU,
                    vendor=normalize_vendor(vendor or "Unknown"),
                    model=normalize_model(model),
                    specs={"metal": str(g.get("spdisplays_metal", "") or "")},
                )
            )
        return out

    def _ram(self, sp: dict[str, list[dict[str, Any]]]) -> list[Component]:
        hw = (sp.get("SPHardwareDataType") or [{}])[0]
        mem = (sp.get("SPMemoryDataType") or [{}])[0] if sp.get("SPMemoryDataType") else {}
        total = hw.get("physical_memory") or mem.get("SPMemoryDataType") or ""
        # ``physical_memory`` arrives as e.g. ``"16 GB"``.
        if not isinstance(total, str) or not total.strip():
            return []
        return [
            Component(
                id="ram-1",
                kind=ComponentKind.RAM,
                vendor="Apple" if "Apple" in str(hw.get("chip_type", "")) else "Unknown",
                model=f"Unified {total}",
                specs={"type": "LPDDR5" if "Apple" in str(hw.get("chip_type", "")) else "Unknown"},
            )
        ]

    def _storage(self, sp: dict[str, list[dict[str, Any]]]) -> list[Component]:
        out: list[Component] = []
        for i, s in enumerate(sp.get("SPStorageDataType", []) or ()):
            name = str(s.get("_name") or "")
            if not name:
                continue
            size = s.get("size_in_bytes") or 0
            out.append(
                Component(
                    id=f"storage-{i + 1}",
                    kind=ComponentKind.STORAGE,
                    vendor=normalize_vendor(str(s.get("physical_drive", {}).get("device_name", "Apple"))),
                    model=name,
                    specs={
                        "capacity_gb": round(int(size) / (1000**3), 2) if size else None,
                        "protocol": str(s.get("physical_drive", {}).get("protocol", "")),
                    },
                )
            )
        return out

    def _os_component(self, sp: dict[str, list[dict[str, Any]]]) -> Component:
        info = self._os_info(sp)
        return Component(
            id="os-1",
            kind=ComponentKind.OS,
            vendor="Apple",
            model=f"{info.family} {info.version}",
            specs={"build": info.build or "", "arch": info.arch or ""},
        )

    def _os_info(self, sp: dict[str, list[dict[str, Any]]]) -> OsInfo:
        sw = (sp.get("SPSoftwareDataType") or [{}])[0]
        full = str(sw.get("os_version") or "")
        family = "macOS"
        version = "unknown"
        build: str | None = None
        if full:
            # e.g. "macOS 14.4.1 (23E224)"
            parts = full.split()
            if len(parts) >= 2:
                family = parts[0]
                version = parts[1]
            if "(" in full and ")" in full:
                build = full[full.find("(") + 1 : full.find(")")]
        arch = (self._run(["uname", "-m"]) or "").strip() or None
        return OsInfo(family=family, version=version, build=build, arch=arch)
