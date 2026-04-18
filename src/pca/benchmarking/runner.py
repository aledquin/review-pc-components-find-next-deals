"""Generic benchmark runner with warm-up, N passes, median + MAD, and env hash."""

from __future__ import annotations

import hashlib
import statistics
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol

from pca.core.errors import BenchmarkError
from pca.core.models import Benchmark


class BenchmarkWrapper(Protocol):
    """Protocol every CPU/GPU/RAM/storage wrapper must implement."""

    @property
    def metric(self) -> str: ...

    @property
    def unit(self) -> str: ...

    def run(self) -> float: ...


@dataclass(frozen=True)
class BenchmarkResult:
    """Typed summary of a successful benchmark run."""

    metric: str
    unit: str
    component_id: str
    samples: tuple[float, ...]
    median: float
    mad: float
    cv_pct: float
    env_hash: str
    ran_at: datetime

    def to_benchmark(self) -> Benchmark:
        return Benchmark(
            id=f"bm-{uuid.uuid4().hex[:10]}",
            component_id=self.component_id,
            metric=self.metric,
            value=self.median,
            unit=self.unit,
            env_hash=self.env_hash,
            ran_at=self.ran_at,
        )


class BenchmarkRunner:
    """Run a ``BenchmarkWrapper`` multiple times and aggregate results.

    Parameters:
        passes: Number of timed passes (must be >= 1). Default 3.
        warmup: Number of warm-up passes discarded before timing. Default 1.
        max_cv_pct: Reject the result if the coefficient of variation across
            timed samples exceeds this value (percent).
    """

    def __init__(
        self,
        passes: int = 3,
        warmup: int = 1,
        max_cv_pct: float = 10.0,
    ) -> None:
        if passes < 1:
            raise ValueError("passes must be >= 1")
        if warmup < 0:
            raise ValueError("warmup must be >= 0")
        self.passes = passes
        self.warmup = warmup
        self.max_cv_pct = max_cv_pct

    def run(
        self,
        wrapper: BenchmarkWrapper,
        *,
        component_id: str,
    ) -> BenchmarkResult:
        for _ in range(self.warmup):
            wrapper.run()

        samples = [wrapper.run() for _ in range(self.passes)]
        if not samples:
            raise BenchmarkError("no samples collected")

        median = float(statistics.median(samples))
        mad = float(statistics.median([abs(s - median) for s in samples]))
        cv = _coefficient_of_variation_pct(samples)
        if cv > self.max_cv_pct:
            raise BenchmarkError(
                f"{wrapper.metric}: coefficient of variation {cv:.2f}% "
                f"exceeds threshold {self.max_cv_pct:.2f}%"
            )

        return BenchmarkResult(
            metric=wrapper.metric,
            unit=wrapper.unit,
            component_id=component_id,
            samples=tuple(samples),
            median=median,
            mad=mad,
            cv_pct=cv,
            env_hash=_env_hash(wrapper.metric),
            ran_at=datetime.now(UTC),
        )


def _coefficient_of_variation_pct(samples: list[float]) -> float:
    if len(samples) < 2:
        return 0.0
    mean = statistics.fmean(samples)
    if mean == 0:
        return 0.0
    stdev = statistics.pstdev(samples)
    return abs(stdev / mean) * 100.0


def _env_hash(metric: str) -> str:
    """Hash a small digest of the run environment. Deterministic within a host.

    For MVP we deliberately exclude wall-clock and random nonces so two
    back-to-back runs on the same host produce identical hashes, which is
    what the TDD suite asserts.
    """
    import platform
    import sys

    payload = "|".join(
        (
            metric,
            platform.system(),
            platform.release(),
            platform.machine(),
            sys.version.split(" ")[0],
        )
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]
