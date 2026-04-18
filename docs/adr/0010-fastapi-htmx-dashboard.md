# 0010 - FastAPI + HTMX + Alpine.js for the local dashboard

- Status: Accepted
- Date: 2026-04-17
- Deciders: @pca-team
- Tags: ui, wave-3

## Context

Wave 3 of the UI roadmap is a local web dashboard. Options ranged from a
fully client-side SPA (React/Vue) to server-rendered HTMX. The dashboard
needs to:

1. Reuse the CLI orchestrator - no business logic duplication.
2. Work offline with zero build step (no webpack, no node toolchain).
3. Embed cleanly inside a Tauri shell later (Wave 4).

## Decision

- **FastAPI** hosts the HTTP API (identical Pydantic schemas as the core).
- **HTMX** drives partial page swaps; **Alpine.js** handles tiny client-side
  state (budget slider, workload select).
- No bundler, no TypeScript. Templates are plain Python f-strings returned as
  `HTMLResponse` for the small set of views we need.
- LAN exposure is off by default. Non-loopback binds require `--token <s>`.

## Consequences

Positive:

- `pip install` and `pca serve` is the only setup: the Tauri shell reuses
  the identical stack.
- Every view is directly testable via `fastapi.testclient` - no Selenium,
  no Playwright for the MVP.
- HTMX partials keep the wire size tiny; same JS-free code path works
  behind corporate proxies and on air-gapped desktops.

Negative:

- Limited client-side interactivity; complex charts require JS sprinkles.
- Alpine.js and HTMX pulled from `unpkg` by default - we vendor pinned
  versions before shipping the Tauri bundle.

## Alternatives considered

- **Tauri + React + Vite**: enough build tooling to double the release-engineering surface.
- **Flask + Jinja + vanilla JS**: possible, but FastAPI's Pydantic integration
  halves the schema plumbing we'd otherwise write.
- **Dash / Streamlit**: heavyweight, poor fit for a Tauri embed later.
