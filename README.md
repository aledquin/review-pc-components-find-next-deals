# PC Upgrade Advisor

A cross-platform (Windows-first) tool that inventories a PC, benchmarks it, compares it to the live US market via official retailer APIs, and produces a budget-optimized upgrade **quote**.

> Windows-first. Linux second. macOS best-effort. US market only in v1.

## Status

MVP under active development. See `docs/architecture.md` and the roadmap in `docs/adr/` for what is in vs. out of scope per wave.

## Quickstart (developers)

```bash
python -m venv .venv
# Windows:
.venv\Scripts\activate
# Linux/macOS:
source .venv/bin/activate

pip install -e ".[dev]"
pytest
```

## UI waves

1. **Wave 1 (MVP)** - CLI (`pca ...`).
2. **Wave 2** - HTML + PDF reports.
3. **Wave 3** - Local web dashboard (FastAPI + HTMX, `127.0.0.1`).
4. **Wave 4** - Desktop GUI (Tauri shell over Wave 3 dashboard).

## Directory layout

See `docs/architecture.md`. The top-level layout is fixed:

```
bin/   lib/   src/pca/   resources/   tests/{units,functionals,data}   docs/   prompts/
```

## CLI cheatsheet (Wave 1)

```bash
pca inventory                       # detect installed hardware
pca bench --quick                   # run CPU/RAM/storage benches
pca report                          # HTML + JSON report of current rig
pca market refresh                  # pull live prices (cache-first)
pca recommend --budget 800 --usd    # upgrade plan within budget
pca quote --budget 800              # itemized quote (JSON in MVP, PDF in Wave 2)
```

## Test strategy

Strict **TDD** (Red -> Green -> Refactor). Fixtures under `tests/data/` are versioned **Known Good Results** (KGRs): 3 reference rigs, 2 market snapshots, and expected reports/quotes per `(rig, budget, snapshot)` triple.

## License

To be decided. All bundled third-party dependencies are permissively licensed (MIT/BSD/Apache/LGPL-dynamic); see `docs/data-sources-tos.md` and the generated SBOM per release.
