"""Linux inventory probe.

Primary source is ``lshw -json`` which, when run as root, exposes most of what
we need in a single pass. We degrade to ``/proc`` + ``/sys`` parsing when
``lshw`` is unavailable or returns partial data. All shell-outs go through a
thin injectable runner so tests can drive the probe with fixtures instead of
the live OS.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from collections.abc import Callable
from pathlib import Path
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
"""Injectable shell-out. Receives argv, returns captured stdout (or ``""``)."""


def _default_runner(argv: list[str]) -> str:
    exe = shutil.which(argv[0])
    if exe is None:
        return ""
    try:
        result = subprocess.run(  # noqa: S603 - argv is controlled by callers
            [exe, *argv[1:]],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
    except (subprocess.TimeoutExpired, OSError):
        return ""
    return result.stdout or ""


class LinuxInventoryProbe:
    """``InventoryProbe`` implementation for Linux hosts."""

    def __init__(
        self,
        *,
        runner: CommandRunner | None = None,
        proc_cpuinfo: Path = Path("/proc/cpuinfo"),
        meminfo: Path = Path("/proc/meminfo"),
        os_release: Path = Path("/etc/os-release"),
    ) -> None:
        self._run = runner or _default_runner
        self._proc_cpuinfo = proc_cpuinfo
        self._meminfo = meminfo
        self._os_release = os_release

    def collect(self) -> SystemSnapshot:
        components: list[Component] = []
        lshw = self._lshw_json()

        components.extend(self._cpus(lshw))
        components.extend(self._gpus(lshw))
        components.extend(self._ram(lshw))
        components.extend(self._motherboards(lshw))
        components.extend(self._storage(lshw))
        components.append(self._os_component())

        if not components:
            raise InventoryError("Linux inventory probe produced no components.")

        return SystemSnapshot(
            id=new_snapshot_id(),
            components=tuple(components),
            benchmarks=(),
            os_info=self._os_info(),
            captured_at=now_utc(),
        )

    # ------------------------------------------------------------------
    # lshw parsing
    # ------------------------------------------------------------------

    def _lshw_json(self) -> dict[str, Any]:
        raw = self._run(["lshw", "-json", "-quiet"])
        if not raw:
            return {}
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return {}
        if isinstance(data, list):
            return data[0] if data else {}
        return data if isinstance(data, dict) else {}

    def _walk(self, node: dict[str, Any]) -> list[dict[str, Any]]:
        stack: list[dict[str, Any]] = [node]
        out: list[dict[str, Any]] = []
        while stack:
            cur = stack.pop()
            if not isinstance(cur, dict):
                continue
            out.append(cur)
            for child in cur.get("children", []) or ():
                stack.append(child)
        return out

    def _nodes_of_class(self, tree: dict[str, Any], class_: str) -> list[dict[str, Any]]:
        return [n for n in self._walk(tree) if n.get("class") == class_]

    # ------------------------------------------------------------------
    # Per-kind builders
    # ------------------------------------------------------------------

    def _cpus(self, lshw: dict[str, Any]) -> list[Component]:
        cpus = self._nodes_of_class(lshw, "processor")
        if not cpus:
            return self._cpus_from_proc()
        out: list[Component] = []
        for i, n in enumerate(cpus):
            specs = {
                "cores": int(n.get("configuration", {}).get("cores", 0) or 0),
                "threads": int(n.get("configuration", {}).get("threads", 0) or 0),
                "max_clock_hz": int(n.get("capacity", 0) or 0),
            }
            out.append(
                Component(
                    id=f"cpu-{i + 1}",
                    kind=ComponentKind.CPU,
                    vendor=normalize_vendor(str(n.get("vendor", "") or "")),
                    model=normalize_model(str(n.get("product", "") or "")),
                    specs={k: v for k, v in specs.items() if v},
                )
            )
        return out

    def _cpus_from_proc(self) -> list[Component]:
        if not self._proc_cpuinfo.exists():
            return []
        text = self._proc_cpuinfo.read_text(encoding="utf-8", errors="ignore")
        model = ""
        vendor = ""
        for line in text.splitlines():
            if ":" not in line:
                continue
            k, _, v = line.partition(":")
            key = k.strip().lower()
            val = v.strip()
            if key == "model name" and not model:
                model = val
            elif key == "vendor_id" and not vendor:
                vendor = val
            if model and vendor:
                break
        if not model:
            return []
        return [
            Component(
                id="cpu-1",
                kind=ComponentKind.CPU,
                vendor=normalize_vendor(vendor or "Unknown"),
                model=normalize_model(model),
                specs={},
            )
        ]

    def _gpus(self, lshw: dict[str, Any]) -> list[Component]:
        displays = self._nodes_of_class(lshw, "display")
        out: list[Component] = []
        for i, n in enumerate(displays):
            product = str(n.get("product", "") or "")
            vendor = str(n.get("vendor", "") or "")
            if not product:
                continue
            out.append(
                Component(
                    id=f"gpu-{i + 1}",
                    kind=ComponentKind.GPU,
                    vendor=normalize_vendor(vendor or "Unknown"),
                    model=normalize_model(product),
                    specs={"driver": str(n.get("configuration", {}).get("driver", "") or "")},
                )
            )
        return out

    def _ram(self, lshw: dict[str, Any]) -> list[Component]:
        banks = [
            n
            for n in self._nodes_of_class(lshw, "memory")
            if n.get("id", "").startswith("bank")
        ]
        if not banks:
            return self._ram_from_meminfo()
        out: list[Component] = []
        for i, bank in enumerate(banks):
            size = int(bank.get("size", 0) or 0)
            clock = int(bank.get("clock", 0) or 0)
            desc = str(bank.get("description", "") or "")
            ram_type = _infer_ddr(desc)
            specs: dict[str, Any] = {
                "capacity_gb": round(size / (1024**3), 2) if size else None,
                "speed_mts": int(clock / 1_000_000) if clock else None,
                "type": ram_type,
            }
            out.append(
                Component(
                    id=f"ram-{i + 1}",
                    kind=ComponentKind.RAM,
                    vendor=normalize_vendor(str(bank.get("vendor", "") or "Unknown")),
                    model=str(bank.get("product", "") or "Unknown").strip(),
                    specs={k: v for k, v in specs.items() if v is not None},
                )
            )
        return out

    def _ram_from_meminfo(self) -> list[Component]:
        if not self._meminfo.exists():
            return []
        text = self._meminfo.read_text(encoding="utf-8", errors="ignore")
        for line in text.splitlines():
            if line.startswith("MemTotal:"):
                kib = int(line.split()[1])
                gb = round(kib / (1024**2), 2)
                return [
                    Component(
                        id="ram-1",
                        kind=ComponentKind.RAM,
                        vendor="Unknown",
                        model=f"Aggregated {gb} GB",
                        specs={"capacity_gb": gb},
                    )
                ]
        return []

    def _motherboards(self, lshw: dict[str, Any]) -> list[Component]:
        cores = self._nodes_of_class(lshw, "bus")
        out: list[Component] = []
        for i, n in enumerate(cores):
            product = str(n.get("product", "") or "")
            if not product:
                continue
            out.append(
                Component(
                    id=f"mb-{i + 1}",
                    kind=ComponentKind.MOTHERBOARD,
                    vendor=normalize_vendor(str(n.get("vendor", "") or "Unknown")),
                    model=product.strip() or "Unknown",
                    specs={"version": str(n.get("version", "") or "")},
                )
            )
            break  # there's effectively one motherboard.
        return out

    def _storage(self, lshw: dict[str, Any]) -> list[Component]:
        disks = [
            n
            for n in self._nodes_of_class(lshw, "disk")
            if "logicalname" in n or "product" in n
        ]
        out: list[Component] = []
        for i, n in enumerate(disks):
            size = int(n.get("size", 0) or 0)
            specs: dict[str, Any] = {
                "capacity_gb": round(size / (1000**3), 2) if size else None,
                "interface": str(n.get("configuration", {}).get("driver", "") or ""),
            }
            out.append(
                Component(
                    id=f"storage-{i + 1}",
                    kind=ComponentKind.STORAGE,
                    vendor=normalize_vendor(str(n.get("vendor", "") or "Unknown")),
                    model=str(n.get("product", "") or "Unknown").strip(),
                    specs={k: v for k, v in specs.items() if v is not None},
                )
            )
        return out

    # ------------------------------------------------------------------
    # OS info
    # ------------------------------------------------------------------

    def _os_component(self) -> Component:
        os_info = self._os_info()
        return Component(
            id="os-1",
            kind=ComponentKind.OS,
            vendor="Linux",
            model=f"{os_info.family} {os_info.version}",
            specs={"build": os_info.build or "", "arch": os_info.arch or ""},
        )

    def _os_info(self) -> OsInfo:
        family = "Linux"
        version = "unknown"
        if self._os_release.exists():
            parsed = _parse_os_release(
                self._os_release.read_text(encoding="utf-8", errors="ignore")
            )
            family = parsed.get("NAME", family)
            version = parsed.get("VERSION_ID", parsed.get("VERSION", version))
        arch = (self._run(["uname", "-m"]) or "").strip() or None
        kernel = (self._run(["uname", "-r"]) or "").strip() or None
        return OsInfo(family=family, version=version, build=kernel, arch=arch)


# ---------------------------------------------------------------------------
# Pure helpers (trivially testable)
# ---------------------------------------------------------------------------


_DDR_HINT = re.compile(r"\bDDR(\d)\b", re.IGNORECASE)


def _infer_ddr(description: str) -> str | None:
    m = _DDR_HINT.search(description)
    return f"DDR{m.group(1)}" if m else None


_KV = re.compile(r'^([A-Z_]+)=(?:"(.*)"|(.*))$')


def _parse_os_release(text: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for line in text.splitlines():
        m = _KV.match(line.strip())
        if not m:
            continue
        key = m.group(1)
        val = m.group(2) if m.group(2) is not None else m.group(3)
        out[key] = val or ""
    return out
