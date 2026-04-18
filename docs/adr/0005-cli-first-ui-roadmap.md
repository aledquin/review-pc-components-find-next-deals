# 0005 - CLI-first UI roadmap

- Status: Accepted
- Date: 2026-04-17
- Tags: ui, roadmap

## Context

The product owner elected a phased UX rollout:

1. Wave 1 - CLI only.
2. Wave 2 - HTML + PDF reports (email/share-link friendly).
3. Wave 3 - Local web dashboard (FastAPI + HTMX + Alpine.js).
4. Wave 4 - Desktop GUI (Tauri wrapping the dashboard).

Alternatives considered:

- **GUI first (Tauri or .NET MAUI)**: reaches non-technical users sooner but
  slows down the back-end iteration we actually need.
- **Electron + React**: familiar, but bundle size and RAM footprint conflict
  with the "runs on modest PCs" promise.
- **Pure web (cloud)**: would break the "no data leaves the machine by
  default" guarantee unless we ship a local-only variant anyway.

## Decision

Follow the phased plan. The CLI is the canonical interface: every future
surface is a thin wrapper over the same orchestrator modules.

## Consequences

- Positive: the CLI acts as our stable programmatic API.
- Positive: automation (cron, CI, packaging smoke tests) is trivial.
- Negative: non-technical early adopters can't use the tool until Wave 3.
- Negative: we must keep `rich` output free of ANSI-only features so that CI
  logs stay legible.

## Follow-ups

- Every Wave 1 subcommand has a functional test under
  `tests/functionals/test_cli.py`.
- Wave 3 adds a `pca serve` subcommand that boots the FastAPI app.
