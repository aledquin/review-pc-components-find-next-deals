"""Windows inventory probe using WMI (+ optional NVML for NVIDIA GPUs).

Imports for the vendor-specific libraries are deferred to ``collect()`` so
that the package loads cleanly on non-Windows hosts (important for CI on
Linux runners and for unit tests that never call this probe).
"""

from __future__ import annotations

import platform
import warnings
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


class WindowsInventoryProbe:
    """Collect a snapshot via WMI and NVML. Only safe to use on Windows."""

    def collect(self) -> SystemSnapshot:
        if platform.system() != "Windows":  # pragma: no cover - guard for misuse
            raise InventoryError("WindowsInventoryProbe requires Windows.")

        try:
            import wmi  # type: ignore[import-not-found]  # noqa: PLC0415
        except ImportError as exc:  # pragma: no cover - depends on env
            raise InventoryError(
                "The 'WMI' package is required. Install the 'windows' extra."
            ) from exc

        c = wmi.WMI()
        components: list[Component] = []
        components.extend(self._cpus(c))
        components.extend(self._gpus(c, _nvml_vram_bytes()))
        components.extend(self._ram(c))
        components.extend(self._motherboards(c))
        components.extend(self._storage(c))
        components.extend(self._cases_psus(c))
        components.append(self._os(c))

        return SystemSnapshot(
            id=new_snapshot_id(),
            components=tuple(components),
            benchmarks=(),
            os_info=self._os_info(c),
            captured_at=now_utc(),
        )

    # ------------------------------------------------------------------
    # WMI helpers. Each returns an iterable of Components so the top-level
    # ``collect`` can build one snapshot in a single pass.
    # ------------------------------------------------------------------

    def _cpus(self, c: Any) -> list[Component]:
        out: list[Component] = []
        for i, p in enumerate(c.Win32_Processor()):
            specs = {
                "cores": int(getattr(p, "NumberOfCores", 0) or 0),
                "threads": int(getattr(p, "NumberOfLogicalProcessors", 0) or 0),
                "socket": str(getattr(p, "SocketDesignation", "") or ""),
                "max_clock_mhz": int(getattr(p, "MaxClockSpeed", 0) or 0),
            }
            out.append(
                Component(
                    id=f"cpu-{i + 1}",
                    kind=ComponentKind.CPU,
                    vendor=normalize_vendor(str(getattr(p, "Manufacturer", "") or "")),
                    model=normalize_model(str(getattr(p, "Name", "") or "")),
                    specs=specs,
                )
            )
        return out

    def _gpus(self, c: Any, nvml_vram: list[int]) -> list[Component]:
        # WMI's Win32_VideoController.AdapterRAM is a uint32 exposed as a
        # signed int, so any card >= ~4 GiB overflows to a bogus (often
        # negative or zero) value. When NVML is available we prefer it for
        # NVIDIA GPUs and fall back to WMI only for plausible positive sizes.
        out: list[Component] = []
        nvml_iter = iter(nvml_vram)
        for i, g in enumerate(c.Win32_VideoController()):
            vendor_raw = str(getattr(g, "AdapterCompatibility", "") or "")
            vendor = normalize_vendor(vendor_raw)
            name = str(getattr(g, "Name", "") or "")
            is_nvidia = "nvidia" in vendor_raw.lower() or "nvidia" in name.lower()

            wmi_bytes = int(getattr(g, "AdapterRAM", 0) or 0)
            vram_bytes: int | None = wmi_bytes if wmi_bytes > 0 else None
            if is_nvidia:
                nvml_bytes = next(nvml_iter, None)
                if nvml_bytes is not None and nvml_bytes > 0:
                    vram_bytes = nvml_bytes

            specs: dict[str, Any] = {
                "vram_gb": round(vram_bytes / (1024**3), 2) if vram_bytes else None,
                "driver_version": str(getattr(g, "DriverVersion", "") or ""),
                "driver_date": str(getattr(g, "DriverDate", "") or ""),
            }
            out.append(
                Component(
                    id=f"gpu-{i + 1}",
                    kind=ComponentKind.GPU,
                    vendor=vendor,
                    model=normalize_model(name),
                    specs={k: v for k, v in specs.items() if v is not None},
                )
            )
        return out

    def _ram(self, c: Any) -> list[Component]:
        out: list[Component] = []
        for i, m in enumerate(c.Win32_PhysicalMemory()):
            capacity = int(getattr(m, "Capacity", 0) or 0)
            specs = {
                "capacity_gb": round(capacity / (1024**3), 2) if capacity else None,
                "speed_mts": int(getattr(m, "Speed", 0) or 0) or None,
                "type": _memory_type(int(getattr(m, "SMBIOSMemoryType", 0) or 0)),
                "bank": str(getattr(m, "BankLabel", "") or ""),
            }
            out.append(
                Component(
                    id=f"ram-{i + 1}",
                    kind=ComponentKind.RAM,
                    vendor=normalize_vendor(str(getattr(m, "Manufacturer", "") or "")),
                    model=str(getattr(m, "PartNumber", "") or "").strip() or "Unknown",
                    specs={k: v for k, v in specs.items() if v is not None},
                )
            )
        return out

    def _motherboards(self, c: Any) -> list[Component]:
        out: list[Component] = []
        for i, b in enumerate(c.Win32_BaseBoard()):
            out.append(
                Component(
                    id=f"mb-{i + 1}",
                    kind=ComponentKind.MOTHERBOARD,
                    vendor=normalize_vendor(str(getattr(b, "Manufacturer", "") or "")),
                    model=str(getattr(b, "Product", "") or "Unknown").strip(),
                    specs={
                        "serial": str(getattr(b, "SerialNumber", "") or ""),
                        "version": str(getattr(b, "Version", "") or ""),
                    },
                )
            )
        return out

    def _storage(self, c: Any) -> list[Component]:
        out: list[Component] = []
        for i, d in enumerate(c.Win32_DiskDrive()):
            size = int(getattr(d, "Size", 0) or 0)
            specs = {
                "capacity_gb": round(size / (1000**3), 2) if size else None,
                "interface": str(getattr(d, "InterfaceType", "") or ""),
                "media_type": str(getattr(d, "MediaType", "") or ""),
            }
            out.append(
                Component(
                    id=f"storage-{i + 1}",
                    kind=ComponentKind.STORAGE,
                    vendor=normalize_vendor(str(getattr(d, "Manufacturer", "") or "")),
                    model=str(getattr(d, "Model", "") or "Unknown").strip(),
                    specs={k: v for k, v in specs.items() if v is not None},
                )
            )
        return out

    def _cases_psus(self, c: Any) -> list[Component]:
        # WMI does not reliably expose case/PSU. We emit placeholder rows the
        # user can edit later. Keeping them ensures the schema is always
        # complete for downstream consumers.
        del c
        return [
            Component(
                id="case-1",
                kind=ComponentKind.CASE,
                vendor="Unknown",
                model="Unknown",
                specs={"note": "WMI cannot detect chassis reliably; please edit."},
            ),
            Component(
                id="psu-1",
                kind=ComponentKind.PSU,
                vendor="Unknown",
                model="Unknown",
                specs={"note": "WMI cannot detect PSU reliably; please edit."},
            ),
        ]

    def _os(self, c: Any) -> Component:
        try:
            o = next(iter(c.Win32_OperatingSystem()))
        except StopIteration:  # pragma: no cover
            return Component(
                id="os-1",
                kind=ComponentKind.OS,
                vendor="Microsoft",
                model="Windows (unknown)",
                specs={},
            )
        return Component(
            id="os-1",
            kind=ComponentKind.OS,
            vendor="Microsoft",
            model=str(getattr(o, "Caption", "Windows") or "Windows").strip(),
            specs={
                "version": str(getattr(o, "Version", "") or ""),
                "build": str(getattr(o, "BuildNumber", "") or ""),
                "arch": str(getattr(o, "OSArchitecture", "") or ""),
            },
        )

    def _os_info(self, c: Any) -> OsInfo:
        try:
            o = next(iter(c.Win32_OperatingSystem()))
        except StopIteration:  # pragma: no cover
            return OsInfo(family="Windows", version="unknown")
        return OsInfo(
            family="Windows",
            version=str(getattr(o, "Version", "") or "unknown"),
            build=str(getattr(o, "BuildNumber", "") or None) or None,
            arch=str(getattr(o, "OSArchitecture", "") or None) or None,
        )


def _nvml_vram_bytes() -> list[int]:
    """Return per-device VRAM sizes in bytes, in NVML enumeration order.

    Returns an empty list when NVML is unavailable, the driver is not
    loaded, or any step fails. Callers must not depend on NVML being
    present — it is an optional enhancement for NVIDIA GPUs only.
    """
    try:
        with warnings.catch_warnings():
            # pynvml has been renamed to nvidia-ml-py and emits a
            # FutureWarning on import; our pytest config escalates
            # warnings to errors, so silence it at the source.
            warnings.simplefilter("ignore", FutureWarning)
            import pynvml  # type: ignore[import-not-found]  # noqa: PLC0415
    except ImportError:
        return []

    try:
        pynvml.nvmlInit()
    except Exception:  # noqa: BLE001 - NVML exposes a bespoke exception hierarchy
        return []
    try:
        count = int(pynvml.nvmlDeviceGetCount())
        sizes: list[int] = []
        for idx in range(count):
            try:
                handle = pynvml.nvmlDeviceGetHandleByIndex(idx)
                sizes.append(int(pynvml.nvmlDeviceGetMemoryInfo(handle).total))
            except Exception:  # noqa: BLE001 - skip individual failures
                sizes.append(0)
        return sizes
    except Exception:  # noqa: BLE001
        return []
    finally:
        try:
            pynvml.nvmlShutdown()
        except Exception:  # noqa: BLE001
            pass


# SMBIOS memory-type codes we care about. Unknown codes map to "Unknown"
# so downstream compatibility checks simply skip them.
_MEMORY_TYPE_CODES: dict[int, str] = {
    20: "DDR",
    21: "DDR2",
    22: "DDR2-FB-DIMM",
    24: "DDR3",
    26: "DDR4",
    34: "DDR5",
}


def _memory_type(code: int) -> str:
    return _MEMORY_TYPE_CODES.get(int(code), "Unknown")


class StubProbe:
    """In-process probe used by tests and by ``--stub`` CLI runs.

    Loads a pre-baked snapshot from ``tests/data/inventories/`` or any JSON
    file that validates as ``SystemSnapshot``. Deterministic and safe to use
    on any OS.
    """

    def __init__(self, snapshot: SystemSnapshot) -> None:
        self._snapshot = snapshot

    def collect(self) -> SystemSnapshot:
        return self._snapshot
