# 0003 - Two budget optimizers: greedy + PuLP ILP

- Status: Accepted
- Date: 2026-04-17
- Tags: algorithms, optimisation

## Context

The core value of the product is a correct, budget-bound upgrade plan. The
problem is a variant of the 0/1 knapsack with slot constraints (one CPU, one
GPU, one motherboard, up to N DIMMs and SSDs), plus a compatibility graph
(socket, RAM type, PSU head-room). Two forces pull in opposite directions:

- End users want an instant answer even on a Raspberry Pi.
- Power users want a provably optimal bundle for large component catalogues.

Alternatives considered:

- **Pure greedy**: fast, easy to explain, but produces dominated solutions in
  ~15% of KGR cases (verified against `expected_quotes/`).
- **Pure ILP**: always optimal, but `PuLP`+CBC takes >2s on some rigs and adds
  a native dependency that complicates packaging.
- **Metaheuristics (simulated annealing, GA)**: overkill for the catalogue
  sizes we care about and hard to debug.

## Decision

Ship **both**:

- `optimize_greedy(snapshot, constraint, items)` is the default and runs in
  <20ms on reference hardware.
- `optimize_ilp(...)` is opt-in via `--strategy ilp` and is recommended when
  the catalogue exceeds ~200 candidates or when the user wants a guarantee.

Both share the same compatibility helpers so we test once.

## Consequences

- Positive: users pick their speed/optimality trade-off explicitly.
- Positive: parity tests (`tests/units/test_optimizer_ilp.py`) compare greedy
  and ILP on every reference rig; non-trivial divergence is caught in CI.
- Negative: CBC is an extra dependency. We already bundle `pulp` which
  auto-installs CBC on pip, so the friction is low but not zero for Windows
  wheels.

## Alternatives revisited when

- Catalogue sizes start crossing 1,000 items per component (we then need to
  prune via product-tier clustering before ILP).
- Users report latency >5s on typical hardware (then we add a solver budget
  and fall back to greedy).
