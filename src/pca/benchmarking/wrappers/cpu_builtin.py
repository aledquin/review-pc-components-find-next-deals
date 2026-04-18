"""Built-in, pure-Python CPU micro-benchmark. Zero third-party deps.

Not a substitute for Geekbench or sysbench; the goal is to provide a
reproducible number (events/sec on a trivial integer workload) so the MVP
works out of the box on any platform. Real benchmarks plug into the same
``BenchmarkWrapper`` protocol.
"""

from __future__ import annotations

import time


class BuiltinCpuWrapper:
    """Run a fixed-work integer workload and return events-per-second."""

    def __init__(self, iterations: int = 2_000_000) -> None:
        self._iterations = iterations

    @property
    def metric(self) -> str:
        return "cpu.builtin.events_per_sec"

    @property
    def unit(self) -> str:
        return "ev/s"

    def run(self) -> float:
        iters = self._iterations
        start = time.perf_counter()
        total = 0
        for i in range(iters):
            total ^= (i * 2654435761) & 0xFFFFFFFF
        elapsed = time.perf_counter() - start
        if elapsed <= 0:
            return float(iters)
        _keep = total  # prevent loop elimination
        del _keep
        return iters / elapsed
