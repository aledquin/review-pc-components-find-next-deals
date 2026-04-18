# 0001 - Python 3.12+ as the single runtime

- Status: Accepted
- Date: 2026-04-17
- Tags: runtime, tooling

## Context

The MVP needs a language that (a) runs on Windows, Linux, and macOS without
cross-compilation, (b) has first-class bindings for WMI/pynvml and the
`sysbench`/`fio` shell-outs, (c) is pleasant for data-heavy work (Pydantic,
PuLP, Jinja2, Hypothesis), and (d) the team already knows.

Alternatives considered:

- **Go** - excellent static binary story and cross-platform HTTP, but hardware
  inventory libraries are thin and PuLP has no Go analogue we want to maintain.
- **Rust** - ideal for the desktop shell (Tauri, later), but the MVP churns
  too quickly to pay Rust's up-front cost.
- **TypeScript / Node** - strong UI story, weak domain-modelling ergonomics
  (Pydantic has no real equivalent yet).

## Decision

Target **Python >= 3.12**. CI runs both 3.12 and 3.14 to flush out warnings
before 3.15 ships.

## Consequences

- Positive: best-in-class libraries across inventory, optimisation, and
  reporting. `match`/`type` syntax improves model code.
- Positive: single `pyproject.toml` manages deps, tools, and packaging.
- Negative: Python startup time (~250 ms) is noticeable for the CLI.
- Negative: shipping a desktop binary means bundling the interpreter (Tauri +
  PyOxidizer/pyapp in Wave 4).

## Alternatives revisited when

- Start-up time becomes a blocker for the web dashboard or desktop shell.
- Any hot path (e.g., benchmark runner) becomes CPU-bound beyond what numpy
  or a tiny C extension can cover.
