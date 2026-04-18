# 0004 - Strict TDD with pytest-socket

- Status: Accepted
- Date: 2026-04-17
- Tags: testing, ci

## Context

The plan mandates Red -> Green -> Refactor. In practice, the optimizer and the
retailer adapters are the two areas most prone to silent drift: the optimizer
because its output is easy to misread, and the adapters because a live API
call can quietly "pass" a test that is actually asserting nothing.

Alternatives considered:

- **Snapshot tests only**: catch drift but not correctness; too permissive.
- **Mock the network globally**: easy to bypass accidentally.
- **Leave network calls in unit tests**: non-starter - it makes CI flaky and
  hides bugs behind a retry policy.

## Decision

- Adopt `pytest-socket` with `disable_socket()` applied to `tests/units/`
  via `conftest.py`. Any unit test that needs network must opt-in with
  `@pytest.mark.network`, which is filtered out of the default CI matrix.
- Functional tests (`tests/functionals/`) use cassettes (`syrupy` snapshots +
  recorded JSON under `tests/data/vcr_cassettes/`). Live recordings are
  refreshed manually on a maintainer workstation.
- Hypothesis is wired into optimizer tests to generate diverse rigs and
  budgets; seeds are printed on failure for reproducibility.

## Consequences

- Positive: CI is deterministic across Windows, Ubuntu, and macOS runners.
- Positive: regressions in adapters are caught at contract level before they
  reach production.
- Negative: cassette refresh is a manual chore. We compensate with a
  quarterly calendar item and a `scripts/refresh-cassettes.py` helper (to be
  added in Wave 2).

## Follow-ups

- Add mutation testing via `mutmut` on `budget/` and `gap_analysis/`.
- Add coverage thresholds per package once the codebase stabilises.
