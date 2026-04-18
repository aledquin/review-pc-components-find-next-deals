"""TDD: unit tests for the benchmark runner.

The runner must:
- Execute a configurable warm-up pass + N timed passes.
- Compute the median and Median Absolute Deviation (MAD).
- Reject runs whose coefficient of variation exceeds a threshold.
- Capture a stable environment hash.
- Never shell out in unit tests (fake wrappers only).
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from pca.benchmarking.runner import BenchmarkResult, BenchmarkRunner, BenchmarkWrapper


class FakeWrapper(BenchmarkWrapper):
    def __init__(self, samples: list[float], name: str = "cpu.fake") -> None:
        self.name = name
        self._samples = list(samples)
        self.calls = 0

    @property
    def metric(self) -> str:
        return self.name

    @property
    def unit(self) -> str:
        return "ev/s"

    def run(self) -> float:
        self.calls += 1
        if not self._samples:
            raise RuntimeError("no samples left")
        return self._samples.pop(0)


class TestRunner:
    def test_warmup_is_discarded(self):
        wrapper = FakeWrapper([999.0, 100.0, 100.0, 100.0])  # warmup outlier
        runner = BenchmarkRunner(passes=3, warmup=1)
        result = runner.run(wrapper, component_id="cpu-1")
        assert isinstance(result, BenchmarkResult)
        assert result.median == 100.0
        assert wrapper.calls == 4  # 1 warmup + 3 timed

    def test_median_of_three(self):
        wrapper = FakeWrapper([50.0, 100.0, 200.0, 150.0])
        runner = BenchmarkRunner(passes=3, warmup=1, max_cv_pct=100.0)
        result = runner.run(wrapper, component_id="cpu-1")
        assert result.median == 150.0

    def test_coefficient_of_variation_calculated(self):
        wrapper = FakeWrapper([0.0, 100.0, 100.0, 100.0])
        runner = BenchmarkRunner(passes=3, warmup=1)
        result = runner.run(wrapper, component_id="cpu-1")
        assert result.cv_pct == pytest.approx(0.0, abs=1e-9)

    def test_env_hash_is_stable_and_hex(self):
        wrapper = FakeWrapper([100.0] * 8)
        runner = BenchmarkRunner(passes=3, warmup=1)
        a = runner.run(wrapper, component_id="cpu-1").env_hash
        b = runner.run(wrapper, component_id="cpu-1").env_hash
        assert a == b
        assert len(a) >= 8
        int(a, 16)

    def test_run_produces_valid_benchmark_entity(self):
        wrapper = FakeWrapper([100.0, 102.0, 98.0, 100.0])
        runner = BenchmarkRunner(passes=3, warmup=1)
        result = runner.run(wrapper, component_id="cpu-1")
        bm = result.to_benchmark()
        assert bm.component_id == "cpu-1"
        assert bm.metric == "cpu.fake"
        assert bm.unit == "ev/s"
        assert bm.value == result.median
        assert bm.ran_at.tzinfo == UTC
        assert isinstance(bm.ran_at, datetime)

    def test_rejects_high_cv(self):
        wrapper = FakeWrapper([0.0, 10.0, 1000.0, 50.0])
        runner = BenchmarkRunner(passes=3, warmup=1, max_cv_pct=5.0)
        with pytest.raises(Exception):
            runner.run(wrapper, component_id="cpu-1")
