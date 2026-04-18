# Prompt: Plan for "PC Upgrade Advisor" Application

> Copy everything below the `---` and paste it into your AI assistant (Cursor, ChatGPT, Claude, etc.) to request a detailed plan. Do **not** ask the assistant to write code yet — the goal of this prompt is a **plan and architecture document**.

---

## Role

You are a **senior software architect and hardware/performance engineer**. Produce a complete, actionable **plan** (no implementation yet) for the project described below. Be opinionated, cite trade-offs, and flag risks.

## Project name

**PC Upgrade Advisor** — a cross-platform application that inspects a user's PC, benchmarks it, compares it to the current market, and recommends the best upgrades for a given budget.

## Functional requirements (user stories)

The app must, end-to-end:

1. **Inventory** — Detect and list all installed PC components (CPU, GPU, RAM, motherboard, storage, PSU, cooling, chassis, peripherals, OS/driver versions).
2. **Performance review** — Measure or estimate current performance per component and as a system (CPU/GPU benchmarks, RAM bandwidth, storage IOPS, thermals, bottleneck analysis).
3. **Deprecation review** — Flag components that are end-of-life, end-of-support, missing driver updates, or on sockets/chipsets no longer in production.
4. **Performance analysis report** — Produce a human-readable report (HTML/PDF + JSON) with scores, charts, bottlenecks, and a plain-English summary.
5. **Market comparison** — Compare each component against current market equivalents (same tier, next tier, best-value tier) using live data.
6. **Gap analysis** — Quantify performance gaps (%, FPS, latency, bandwidth) between the user's rig and the market reference rigs at similar price points.
7. **Replacement recommendations** — Rank components that should be replaced, ordered by performance-per-dollar uplift and by removing the biggest bottleneck first.
8. **Budget-aware filtering** — Accept a budget (and optional constraints: form factor, socket, PSU wattage, case clearance, preferred brands, noise, power draw) and return the **best upgrade bundle** that maximizes performance within the budget. Support multiple budget tiers (e.g., minimum viable, sweet spot, no-compromise).
9. **Price & deals scraping** — Query multiple retailers/aggregators for current prices, stock, shipping, and active deals/coupons. Respect robots.txt, rate limits, and regional availability.
10. **Quote generation** — Produce a final quote (itemized + total, tax/shipping estimates, links, expiry of deal) as PDF and shareable link.

## Non-functional requirements

- Cross-platform: **Windows first**, Linux second, macOS best-effort.
- Offline-capable core (inventory + benchmarks); online features degrade gracefully.
- Privacy: no telemetry by default, all hardware data stays local unless user opts in.
- Deterministic, reproducible benchmark runs (seeded, warm-up, multiple passes, outlier rejection).
- Internationalization-ready (currency, locale, units).
- Observability: structured logs, metrics, error reporting.
- Security: sandboxed scrapers, signed releases, SBOM.

## What I want from you (deliverables, in this order)

1. **Executive summary** (½ page).
2. **Recommended platform / tech stack** with justification and at least one credible alternative per choice. Address:
   - Language(s) & runtime
   - Hardware-inventory libraries per OS (WMI, `lshw`, `dmidecode`, `libpci`, `nvml`, `system_profiler`, etc.)
   - Benchmark tooling (built-in vs. wrapping established tools like Geekbench, 3DMark, Cinebench, CrystalDiskMark, `sysbench`, `fio`, `stress-ng`)
   - Price/deal data sources (official APIs where possible: Amazon PA-API, Newegg, Best Buy, PCPartPicker, Keepa, Geizhals; fallback scraping strategy)
   - UI (desktop: Tauri/Electron/.NET MAUI/Qt; or web dashboard + local agent)
   - Storage (SQLite for local, Postgres if server component)
   - Packaging & auto-update
3. **High-level architecture diagram** (ASCII or Mermaid) with modules and data flow.
4. **Domain model** — entities (Component, Benchmark, Report, MarketItem, Deal, Quote, BudgetConstraint, UpgradePlan) and their relationships.
5. **Module breakdown** mapped to the directory layout below.
6. **Algorithms** for:
   - Bottleneck detection
   - Performance scoring & normalization across generations
   - Budget optimization (knapsack / ILP / greedy with compatibility constraints) — compare approaches.
   - Deal ranking (price, reputation, shipping, warranty, deal freshness).
7. **Data sources plan** — for each source: API vs. scrape, auth, rate limits, ToS considerations, caching strategy, fallback.
8. **Test strategy (TDD-first)** — see "Testing" section below.
9. **Directory structure** — exactly matching the layout below, with a one-line purpose for every folder and key file.
10. **Milestone roadmap** — phased delivery (MVP → v1 → v1.x) with exit criteria per phase.
11. **Risk register** — technical, legal (scraping ToS), data-freshness, hardware-detection edge cases, and mitigations.
12. **Enhancements & stretch goals** — your own recommendations beyond my list (e.g., thermal/noise modeling, power-bill estimation, resale value of replaced parts, community benchmark database, CLI + GUI + REST API parity, plugin system for new retailers, LLM-powered natural-language "why this upgrade" explainer, energy efficiency score, used-market comparison, warranty tracker).

## Testing (TDD, mandatory)

Follow strict **Red → Green → Refactor**. In the plan, specify:

- **Unit tests** (`tests/units`) — pure logic: scoring, budget optimizer, parsers, normalizers. Fast, no I/O.
- **Functional tests** (`tests/functionals`) — end-to-end flows with fakes/mocks for hardware probes and network: "given this rig + $800 budget, produce this upgrade plan".
- **Test data / KGRs** (`tests/data`) — **Known Good Results** (golden files): canned hardware inventories, canned market snapshots, canned expected reports & quotes. All fixtures versioned and human-readable (JSON/YAML). Include at least 3 reference rigs (budget, mid, high-end) and 2 market snapshots (normal, deal-heavy).
- Coverage target, mutation-testing recommendation, property-based testing for the optimizer, contract tests for each retailer adapter.
- CI matrix (OS × runtime versions), lint, type-check, security scan (SCA + SBOM), and a "no network in unit tests" guard.

## Required directory structure

Produce the plan around **exactly** this layout and explain what goes where:

```
.
├── bin/                  # CLI entry points & launcher scripts
├── lib/                  # Third-party or vendored libraries (if any)
├── src/                  # Application source code (modules grouped by bounded context)
│   ├── inventory/
│   ├── benchmarking/
│   ├── deprecation/
│   ├── reporting/
│   ├── market/
│   ├── gap_analysis/
│   ├── recommender/
│   ├── budget/
│   ├── deals/
│   ├── quoting/
│   ├── core/             # shared domain models, utils, logging, config
│   └── ui/               # GUI / web front-end / CLI presenters
├── resources/            # Static assets: icons, report templates, locale files, component catalogs
├── tests/
│   ├── units/
│   ├── functionals/
│   └── data/             # KGRs: golden inventories, market snapshots, expected reports/quotes
├── docs/                 # Architecture, ADRs, user manual
└── prompts/              # This file and other prompt assets
```

## Constraints on your answer

- Do **not** write application code. Pseudocode and interface sketches are welcome.
- Do **not** hand-wave legal/ToS issues around scraping — call them out explicitly.
- Every major choice must include a one-line trade-off.
- Prefer open standards and permissive licenses; flag any GPL/commercial dependency.
- Be explicit about what the **MVP** excludes.

## Output format

Return the plan as a single Markdown document with the numbered sections above, using headings, tables for comparisons, Mermaid for diagrams, and checklists for milestones. End with an **"Open questions for the product owner"** section (max 10 questions).

---
