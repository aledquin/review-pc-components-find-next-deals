"""Shell-out wrappers for ``sysbench`` and ``fio``.

These wrappers do NOT run in unit tests (network + subprocess are blocked).
They are exercised in functional tests behind ``@pytest.mark.slow`` where
the tool is actually installed.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

from pca.core.errors import BenchmarkError


class SysbenchCpuWrapper:
    """Wrap ``sysbench cpu --threads=N run`` and parse events/sec."""

    def __init__(self, threads: int = 1, max_prime: int = 20000) -> None:
        self._threads = threads
        self._max_prime = max_prime

    @property
    def metric(self) -> str:
        return "cpu.sysbench.events_per_sec"

    @property
    def unit(self) -> str:
        return "ev/s"

    def run(self) -> float:
        if shutil.which("sysbench") is None:
            raise BenchmarkError("sysbench is not installed on PATH")
        proc = subprocess.run(  # noqa: S603 - sysbench is a trusted local tool
            [
                "sysbench",
                "cpu",
                f"--threads={self._threads}",
                f"--cpu-max-prime={self._max_prime}",
                "--time=5",
                "run",
            ],
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
        )
        if proc.returncode != 0:
            raise BenchmarkError(f"sysbench failed: {proc.stderr[:200]}")
        match = re.search(r"events per second:\s*([0-9.]+)", proc.stdout)
        if not match:
            raise BenchmarkError("could not parse sysbench output")
        return float(match.group(1))


class FioRandReadWrapper:
    """Wrap ``fio`` for a 4K random-read IOPS measurement."""

    def __init__(self, target: Path, size_mb: int = 256) -> None:
        self._target = target
        self._size_mb = size_mb

    @property
    def metric(self) -> str:
        return "storage.fio.iops_4k_randread"

    @property
    def unit(self) -> str:
        return "iops"

    def run(self) -> float:
        if shutil.which("fio") is None:
            raise BenchmarkError("fio is not installed on PATH")
        proc = subprocess.run(  # noqa: S603 - fio is a trusted local tool
            [
                "fio",
                "--name=pca-randread",
                f"--filename={self._target}",
                f"--size={self._size_mb}M",
                "--rw=randread",
                "--bs=4k",
                "--iodepth=16",
                "--numjobs=1",
                "--runtime=10",
                "--time_based",
                "--direct=0",
                "--output-format=json",
            ],
            capture_output=True,
            text=True,
            check=False,
            timeout=60,
        )
        if proc.returncode != 0:
            raise BenchmarkError(f"fio failed: {proc.stderr[:200]}")
        import json  # local import keeps startup lean

        try:
            data = json.loads(proc.stdout)
            return float(data["jobs"][0]["read"]["iops"])
        except (KeyError, IndexError, ValueError) as exc:
            raise BenchmarkError("could not parse fio output") from exc
