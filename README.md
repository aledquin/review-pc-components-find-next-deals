# PC Upgrade Advisor

A cross-platform (Windows-first) tool that inventories a PC, benchmarks it, compares it to the live US market via official retailer APIs, and produces a budget-optimized upgrade **quote**.

> Windows-first. Linux second. macOS best-effort. US market only in v1.

## Status

Waves 1-4 are implemented. Wave 1 (CLI) + Wave 2 (HTML/PDF + charts + Linux probe) + Wave 3 (FastAPI/HTMX dashboard + eBay/Newegg adapters + per-ZIP tax) + Wave 4 (macOS probe + Tauri scaffolding) + v1.x extensions (multi-objective optimizer, LLM explainer, retailer plugin SDK, used-market adapter) are shipped. Tauri signing/release engineering is still in progress. See `docs/architecture.md` and the ADR index in `docs/adr/README.md`.

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

1. **Wave 1 (MVP) - shipped** - CLI (`pca ...`).
2. **Wave 2 - shipped** - HTML + PDF reports, matplotlib charts, Linux probe.
3. **Wave 3 - shipped** - Local web dashboard (FastAPI + HTMX, `127.0.0.1`) via `pca serve`.
4. **Wave 4 - scaffolded** - Desktop GUI (Tauri shell over Wave 3 dashboard); see `desktop/README.md`.

## Directory layout

See `docs/architecture.md`. The top-level layout is fixed:

```
bin/   lib/   src/pca/   resources/   tests/{units,functionals,data}   docs/   prompts/
```

## CLI cheatsheet

```bash
pca inventory                       # detect installed hardware
pca bench --quick                   # run CPU/RAM/storage benches
pca report                          # HTML + JSON (+ PDF with the reporting extra)
pca market refresh                  # pull live prices (cache-first)
pca recommend --budget 800 --strategy multi   # greedy | ilp | multi
pca quote --budget 800 --zip 10001            # itemized quote with per-ZIP tax
pca serve --host 127.0.0.1 --port 8765        # FastAPI + HTMX dashboard
```

## Optional extras

| Extra          | Purpose                                                   |
| -------------- | --------------------------------------------------------- |
| `reporting`    | `matplotlib` + `weasyprint` for PNG charts and PDF output |
| `web`          | `fastapi` + `uvicorn` for `pca serve`                     |
| `linux`        | `lshw` helpers (no Python package; install via apt)       |
| `explainer`    | `httpx` client for Ollama / OpenAI LLM explainers         |

## Plugin SDK

Third-party retailer adapters register under the entry-point group
`pc_upgrade_advisor.market_adapters`. Run `check_conformance(adapter)` in your
plugin's test suite and set `PCA_ALLOW_PLUGINS=true` to load installed
plugins. See ADR 0012 for the threat model.

## Test strategy

Strict **TDD** (Red -> Green -> Refactor). Fixtures under `tests/data/` are versioned **Known Good Results** (KGRs): 3 reference rigs, 2 market snapshots, and expected reports/quotes per `(rig, budget, snapshot)` triple.

## License

To be decided. All bundled third-party dependencies are permissively licensed (MIT/BSD/Apache/LGPL-dynamic); see `docs/data-sources-tos.md` and the generated SBOM per release.
