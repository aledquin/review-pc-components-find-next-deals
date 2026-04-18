# PC Upgrade Advisor - User Guide

This guide walks you through every way to use the app - CLI, local web
dashboard, and the (scaffolded) desktop shell - plus configuration,
retailer integrations, and troubleshooting.

> Windows-first, Linux second, macOS best-effort. US market only in v1.
> Everything runs locally by default; no telemetry, no cloud calls unless
> you explicitly enable them.

- [1. Install](#1-install)
- [2. Configure](#2-configure)
- [3. Quickstart (3 minutes)](#3-quickstart-3-minutes)
- [4. CLI reference](#4-cli-reference)
- [5. Web dashboard (`pca serve`)](#5-web-dashboard-pca-serve)
- [5.5 Native GUI (`pca gui`)](#55-native-gui-pca-gui--pca-guiexe)
- [6. Desktop shell (Tauri)](#6-desktop-shell-tauri)
- [7. Reports and quotes](#7-reports-and-quotes)
- [8. Retailer adapters and plugins](#8-retailer-adapters-and-plugins)
- [9. LLM "why this upgrade" explainer](#9-llm-why-this-upgrade-explainer)
- [10. Privacy, security, and ToS](#10-privacy-security-and-tos)
- [11. Troubleshooting](#11-troubleshooting)
- [12. Glossary](#12-glossary)

---

## 1. Install

> **Fastest path:** download a prebuilt executable from the
> [Releases page](https://github.com/example/pc-upgrade-advisor/releases)
> and skip straight to [§3](#3-quickstart-3-minutes). Windows, Linux, and
> macOS binaries are attached to every tagged release.

### 1.0 Prebuilt executables (no Python needed)

Two flavors per platform: a **CLI** (headless) and a **GUI** (native
window, no browser). Both are fully self-contained - they bundle the
Python runtime, all dependencies, and the full `resources/` tree.

| Flavor | Platform | Artefact                      | Size   | How to run |
| ------ | -------- | ----------------------------- | ------ | ---------- |
| CLI    | Windows  | `pca-windows-x64.exe`         | ~50 MB | `pca-windows-x64.exe --help` |
| CLI    | Linux    | `pca-linux-x64`               | ~50 MB | `chmod +x ... && ./pca-linux-x64 --help` |
| CLI    | macOS    | `pca-macos-universal`         | ~50 MB | `chmod +x ... && ./pca-macos-universal --help` |
| GUI    | Windows  | `pca-gui-windows-x64.exe`     | ~80 MB | Double-click. Native window, taskbar icon, no console. |
| GUI    | Linux    | `pca-gui-linux-x64`           | ~80 MB | `./pca-gui-linux-x64` (requires X11 or Wayland) |
| GUI    | macOS    | `pca-gui-macos-universal`     | ~80 MB | Double-click. First launch may need `xattr -d com.apple.quarantine ./pca-gui-macos-universal` |

**Which do I want?**

- **CLI (`pca`)** - scripting, automation, one-shot reports, CI pipelines.
  7 subcommands (`inventory`, `bench`, `report`, `market`, `recommend`,
  `quote`, `serve`, `gui`).
- **GUI (`pca-gui`)** - double-click launcher for non-technical users.
  Three tabs (Inventory, Recommend, Quote), File menu, export to HTML.
  Pure native Win32 / Cocoa / Qt widgets - no browser, no URL bar.

Things **not** in the default binaries (to keep size down):

- `weasyprint` - PDF export. Reports still emit HTML + JSON.
- `matplotlib` - embedded report charts. The HTML templates degrade gracefully.

If you want PDF/charts, use the source install below.

### 1.1 Prerequisites (source install only)

| OS       | Needs                                                              |
| -------- | ------------------------------------------------------------------ |
| Windows  | Python 3.12+, PowerShell 5.1+                                      |
| Linux    | Python 3.12+, `lshw` (optional but recommended), apt/dnf/pacman    |
| macOS    | Python 3.12+, Xcode CLT (for `sysctl`)                             |

Optional system packages for the **PDF** feature on Linux (WeasyPrint):

```bash
sudo apt-get install -y libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz0b \
                        libcairo2 libffi-dev
```

### 1.2 Install from source

```bash
git clone https://github.com/<your-org>/pc-upgrade-advisor.git
cd pc-upgrade-advisor

python -m venv .venv
# Windows
.venv\Scripts\activate
# Linux / macOS
source .venv/bin/activate

pip install -e ".[dev]"      # core + tests
```

### 1.3 Optional extras

Install only what you need:

| Extra       | Installs                          | Enables                                 |
| ----------- | --------------------------------- | --------------------------------------- |
| `reporting` | `matplotlib`, `weasyprint`        | PNG charts in reports, PDF export       |
| `web`       | `fastapi`, `uvicorn`, `httpx`     | `pca serve` local dashboard             |
| `gui`       | `PyQt6`                           | `pca gui` native desktop window         |
| `linux`     | (no Python deps; docs-only)       | Installs the `lshw`-based probe path    |
| `explainer` | `httpx` (Ollama/OpenAI transport) | Natural-language upgrade explanations   |
| `packaging` | `pyinstaller`                     | Build `pca.exe` / `pca-gui.exe` locally |

Combine them:

```bash
pip install -e ".[dev,reporting,web,gui,explainer]"
```

### 1.4 Verify

```bash
pca --help             # should list 7 commands
pytest -q              # 189 passing, 1 skipped if weasyprint missing
```

### 1.5 Build your own executable

Source checkout + one command:

```powershell
# Windows
.\packaging\build_exe.ps1
```

```bash
# Linux / macOS
./packaging/build_exe.sh
```

Output lands at `dist/pca.exe` (Windows) or `dist/pca`. The spec file at
`packaging/pca.spec` is the single source of truth for what goes into
the bundle; edit it to enable/disable heavy optionals (matplotlib,
weasyprint) by removing them from the `excludes` list.

CI publishes signed artefacts on every `v*` git tag via
`.github/workflows/release.yml`.

---

## 2. Configure

All settings come from environment variables (prefix `PCA_`) or a local
`.env` file. Copy the template and edit:

```bash
cp .env.example .env
```

### 2.1 Settings reference

| Variable                    | Default                 | Purpose                                  |
| --------------------------- | ----------------------- | ---------------------------------------- |
| `PCA_LOG_LEVEL`             | `INFO`                  | `DEBUG`, `INFO`, `WARNING`, `ERROR`      |
| `PCA_CACHE_DIR`             | platform cache dir      | Where the SQLite market cache lives      |
| `PCA_REPORT_DIR`            | platform data dir       | Default output folder for reports/quotes |
| `PCA_ENABLE_SCRAPERS`       | `false`                 | Opt-in to scraping fallbacks (ADR 0007)  |
| `PCA_ALLOW_PLUGINS`         | `false`                 | Load third-party retailer plugins        |
| `PCA_ALLOW_CLOUD_LLM`       | `false`                 | Allow `OpenAIExplainer` to run           |

### 2.2 Retailer credentials (all optional)

| Variable                   | Source                                      |
| -------------------------- | ------------------------------------------- |
| `PCA_BESTBUY_API_KEY`      | https://developer.bestbuy.com/              |
| `PCA_AMAZON_ACCESS_KEY`    | Amazon PA-API 5 associate account           |
| `PCA_AMAZON_SECRET_KEY`    | "                                           |
| `PCA_AMAZON_ASSOC_TAG`     | "                                           |
| `PCA_EBAY_CLIENT_ID`       | https://developer.ebay.com                  |
| `PCA_EBAY_CLIENT_SECRET`   | "                                           |
| `PCA_KEEPA_API_KEY`        | https://keepa.com (optional premium)        |

Missing credentials do not break the app - the corresponding adapter stays
inert and the registry routes around it.

### 2.3 Deal-ranker weights

Tune how deals are sorted (defaults calibrated against KGRs):

```bash
PCA_DEAL_WEIGHT_PRICE=0.5
PCA_DEAL_WEIGHT_REPUTATION=0.2
PCA_DEAL_WEIGHT_SHIPPING=0.1
PCA_DEAL_WEIGHT_WARRANTY=0.1
PCA_DEAL_WEIGHT_FRESHNESS=0.1
```

---

## 3. Quickstart (3 minutes)

Every command below accepts `--stub` to skip the live hardware probe and
use a fixture - useful on Linux/macOS in the MVP, or for reproducing a
specific rig.

```bash
# 1) See what's in your PC (live on Windows, or --stub elsewhere)
pca inventory --stub tests/data/inventories/rig_mid.json --out snap.json

# 2) Generate a report (HTML + JSON, PDF if reporting extra installed)
pca report --stub snap.json --out-dir out/

# 3) Peek at a market snapshot
pca market --market tests/data/market_snapshots/snapshot_normal.json

# 4) Ask for an $800 upgrade plan
pca recommend --stub snap.json \
              --market tests/data/market_snapshots/snapshot_normal.json \
              --budget 800 --strategy multi

# 5) Turn it into a quote (adds tax + shipping)
pca quote --stub snap.json \
          --market tests/data/market_snapshots/snapshot_normal.json \
          --budget 800 --zip 10001 --out-dir out/

# 6) Or open the web dashboard instead
pca serve --stub snap.json \
          --market tests/data/market_snapshots/snapshot_normal.json
# -> visit http://127.0.0.1:8765
```

---

## 4. CLI reference

Run `pca --help` for the top-level list and `pca <command> --help` for
per-command flags.

### 4.1 `pca inventory`

Detect installed hardware and print a summary table.

```bash
pca inventory                                  # live probe
pca inventory --stub rig.json                  # replay a saved snapshot
pca inventory --out snap.json                  # persist it for later commands
```

**Windows**: uses WMI + NVML; runs as your user (no admin needed).
**Linux**: tries `lshw -json` first, falls back to `/proc` + `/sys` +
`uname`. Running without `sudo` gives a partial snapshot.
**macOS**: uses `system_profiler -json` + `sysctl`. Informational only -
benchmark interpretation is not tuned for Apple Silicon.

### 4.2 `pca bench`

Tiny built-in CPU benchmark that exercises the `BenchmarkRunner` pipeline.

```bash
pca bench --quick        # ~1 s
pca bench --full         # ~5-10 s, lower CV
```

Prints median, MAD (median absolute deviation), and CV% so you can judge
the run quality.

### 4.3 `pca report`

Write an HTML + JSON (+ PDF) report to `--out-dir` (defaults to the
platform data dir). Deprecation warnings are printed to the console.

```bash
pca report --stub snap.json --out-dir out/
```

### 4.4 `pca market`

Summarize a cached market snapshot fixture. Live API refresh is
per-adapter (see [§8](#8-retailer-adapters-and-plugins)).

```bash
pca market --market tests/data/market_snapshots/snapshot_normal.json
```

### 4.5 `pca recommend`

Compute an `UpgradePlan` under a USD cap.

```bash
pca recommend \
  --stub snap.json \
  --market tests/data/market_snapshots/snapshot_normal.json \
  --budget 800 \
  --workload gaming_1440p \
  --strategy greedy        # greedy | ilp | multi
```

Strategies:

| Strategy | When to use                                                      |
| -------- | ---------------------------------------------------------------- |
| `greedy` | Fast, always-feasible baseline. Ranks by perf-per-dollar.        |
| `ilp`    | Optimal under linear constraints; uses PuLP + CBC (no network).  |
| `multi`  | Pareto front over perf / power / noise (brute force, <= ~20 candidates). |

Workloads affect the weighted uplift calculation:
`gaming_1080p`, `gaming_1440p`, `gaming_4k`, `productivity`,
`content_creation`, `ml_workstation`.

### 4.6 `pca quote`

End-to-end pipeline - runs `recommend` internally, then adds estimated
tax (by ZIP) and shipping, and writes HTML + JSON (+ PDF).

```bash
pca quote \
  --stub snap.json \
  --market tests/data/market_snapshots/snapshot_normal.json \
  --budget 1200 --zip 98101 --out-dir out/
```

Tax rates come from `resources/catalogs/us_tax_rates.yaml`. Unknown ZIPs
fall back to the national average.

### 4.7 `pca serve`

Launch the FastAPI + HTMX dashboard. See [§5](#5-web-dashboard-pca-serve).

```bash
pca serve --stub snap.json \
          --market tests/data/market_snapshots/snapshot_normal.json \
          --host 127.0.0.1 --port 8765
```

### 4.8 `pca gui`

Launch the native PyQt6 desktop window. See [§5.5](#55-native-gui-pca-gui--pca-guiexe).
Requires the `gui` extra (`pip install -e ".[gui]"`) or the prebuilt
`pca-gui-*` binary.

```bash
pca gui                                     # empty window, use File menu
pca gui --stub snap.json --market m.json    # pre-load fixtures
```

---

## 5. Web dashboard (`pca serve`)

### 5.1 Start it

```bash
pca serve --stub snap.json --market snapshot.json
# -> http://127.0.0.1:8765
```

By default the server only accepts connections from `localhost`. To
expose it on your LAN you **must** provide a shared secret:

```bash
pca serve --host 0.0.0.0 --port 8765 --token "$(openssl rand -hex 16)" \
          --stub snap.json --market snapshot.json
```

Remote clients send the token in an `x-pca-token` header on every
request; loopback requests bypass the check.

### 5.2 What's on the page

- **Plan panel** - Budget input, workload picker, strategy selector
  (`greedy` / `ilp` / `multi`). Click **Recommend** to swap an HTMX
  partial into `#plan`.
- **Inventory panel** - Click **Load** to pull `/api/inventory` as JSON
  for the currently configured snapshot.
- **Disclaimer** - "Local preview - data does not leave this machine by
  default." Override with `ServerConfig.ui_disclaimer` when embedding.

### 5.3 HTTP API

Auto-generated OpenAPI docs live at `/api`. Key endpoints:

| Method + Path         | Purpose                                           |
| --------------------- | ------------------------------------------------- |
| `GET /health`         | Liveness probe (`{"status":"ok"}`)                |
| `GET /`               | HTMX shell (HTML)                                 |
| `GET /api/inventory`  | SystemSnapshot JSON + deprecation findings        |
| `POST /api/recommend` | Return an `UpgradePlan` for the posted body       |
| `POST /api/quote`     | Return a full `Quote` (accepts `?zip_code=...`)   |
| `GET /htmx/plan`      | HTML fragment of the plan (used by HTMX)          |

`POST /api/recommend` request body:

```json
{
  "budget_usd": "800.00",
  "workload": "gaming_1440p",
  "strategy": "multi",
  "socket": "AM5",
  "ram_type": "DDR5"
}
```

`socket` / `ram_type` are optional; when omitted they're inferred from
the snapshot.

### 5.4 Detect this PC from the web dashboard

The Inventory card now has two buttons:

- **Detect this PC** - posts to `/htmx/detect`, which runs the native
  probe in-process and caches the snapshot on the app. All subsequent
  `/api/inventory` / `/htmx/plan` / `/htmx/quote` calls see the live
  machine until the server restarts.
- **Load configured snapshot** - reads the on-disk file the server was
  started with via `--stub`.

The browser asks for confirmation before running the probe. If you
started `pca serve` **without** a `--stub` file, the Detect button is
the only way to populate the dashboard.

### 5.5 Stop it

`Ctrl-C` in the terminal where `pca serve` is running.

---

## 5.5 Native GUI (`pca gui` / `pca-gui.exe`)

If you'd rather not use a browser, ship `pca-gui` - a real native
Win32 / Cocoa / Qt desktop app with actual native widgets. No browser,
no URL bar, no HTML in the main window. Same core pipeline as the CLI
and web dashboard - just a different presenter.

### Launching

- **Prebuilt exe** - double-click `pca-gui-windows-x64.exe` (or the
  Linux / macOS equivalent). No install, no Python, no virtualenv.
- **From source** - `pip install -e ".[gui]"` then `pca gui`.
- **Pre-load fixtures** - `pca gui --stub snap.json --market market.json`.

### What you get

- **File menu** - `Open snapshot ...` (`Ctrl+O`), `Open market
  snapshot ...` (`Ctrl+M`), `Export HTML report ...`, `Quit`
  (`Ctrl+Q`).
- **Inventory tab** - hardware table, deprecation warnings inline at
  the top, plus three action buttons:
  - **Detect this PC** - runs the native hardware probe (WMI on
    Windows, lshw on Linux, system_profiler on macOS) on a background
    thread so the UI stays responsive. The progress bar animates while
    the scan runs (2-5 s typical).
  - **Save as JSON ...** - persists the active snapshot to disk so you
    can reuse it later via `File > Open snapshot...` or the CLI.
  - **Load snapshot ...** - opens a previously saved snapshot file.
- **Recommend tab** - budget spinner, workload combo, strategy combo
  (`greedy` / `ilp` / `multi`), plan table with uplift %, rationale.
- **Quote tab** - same inputs plus a ZIP field for US tax, totals
  panel (subtotal / tax / shipping / grand total), `Export HTML + JSON`
  button.
- **Status bar** - shows the currently loaded snapshot and market file.

Everything stays local - the GUI does not ship telemetry and does not
reach out to retailer APIs unless you've configured credentials.

---

## 6. Desktop shell (Tauri)

**Status: scaffolding only** (see ADR 0011). The code lives under
`desktop/`. When built, it produces a native window that wraps the Wave 3
dashboard and ships an auto-updater.

> **Note**: for most end users, `pca-gui` (above) is a simpler path -
> single self-contained `.exe`, no Rust toolchain needed, no network
> round-trip, real native widgets. Use the Tauri shell only if you
> want the HTMX dashboard in a native window + auto-updates.

### 6.1 What it does (by design)

1. On launch, spawns the bundled `pca-sidecar` (PyInstaller build of
   `pca serve`) on `127.0.0.1:8765` with an ephemeral per-launch token.
2. Shows `desktop/index.html` as a splash screen that polls `/health`.
3. Once the sidecar is healthy, the webview navigates to the dashboard.
   The token is injected via `window.__PCA_TOKEN` and attached to every
   HTMX request as `x-pca-token`.
4. On app shutdown, the sidecar is terminated cleanly.

### 6.2 Building locally (contributors)

```bash
# Requires Rust 1.77+ and the Tauri prereqs for your OS
cd desktop
cargo tauri dev     # run in dev mode with live sidecar
cargo tauri build   # produce installer(s)
```

Release builds are signed / notarized by the CI pipeline - see ADR 0011
for the signing posture. Until the release workflow ships a signed
binary, end users should use `pca serve` directly.

---

## 7. Reports and quotes

### 7.1 Outputs

Each `report` / `quote` run writes to the `out-dir` (or
`PCA_REPORT_DIR` / platform default):

```
out/
├── report-<snapshot-id>.html    # embeds matplotlib charts as data URLs
├── report-<snapshot-id>.json    # machine-readable twin of the HTML
├── report-<snapshot-id>.pdf     # only if the 'reporting' extra is installed
├── quote-<snapshot-id>-<budget>.html
├── quote-<snapshot-id>-<budget>.json
└── quote-<snapshot-id>-<budget>.pdf
```

### 7.2 What's inside

- **Report**: components, per-component catalog/benchmark scores,
  workload-weighted overall score, bottleneck callouts, deprecation
  warnings, chart images.
- **Quote**: the chosen upgrade plan itemized with links and deal
  expiry, then tax + shipping + grand total.

Both HTML templates live under `resources/templates/*.j2` and can be
customized; the JSON twin is the stable format for downstream tools.

### 7.3 PDF

PDF output requires the `reporting` extra. If WeasyPrint can't import
(e.g., missing Cairo/Pango on Windows), the CLI silently drops the PDF
and still writes HTML + JSON. Install system deps per
[§1.1](#11-prerequisites) and the `reporting` extra per
[§1.3](#13-optional-extras).

---

## 8. Retailer adapters and plugins

### 8.1 First-party adapters

| Adapter               | Mode              | Notes                                         |
| --------------------- | ----------------- | --------------------------------------------- |
| Best Buy Developer    | Official API      | Needs `PCA_BESTBUY_API_KEY`                   |
| Amazon PA-API 5       | Official API stub | Production creds required; stub is offline    |
| eBay Browse           | Official API      | OAuth2 client credentials                     |
| eBay Sold (Insights)  | Official API      | Used-market price stats (median / p25 / p75)  |
| Newegg affiliate feed | Local CSV/TSV     | Scraping is **not** supported (ToS)           |

All adapters implement the `MarketAdapter` protocol and register with
`AdapterRegistry`. Missing credentials are never fatal - the registry
just skips that source.

### 8.2 Refreshing prices

Live refresh is per-adapter; run your adapter's refresh routine (e.g.,
in a script) and point `pca market --market <snapshot.json>` at the
output. A `pca market refresh` one-shot will land when credentials are
required less often.

### 8.3 Writing a plugin

Third-party plugins register under the entry-point group
`pc_upgrade_advisor.market_adapters`:

```toml
# your-plugin/pyproject.toml
[project.entry-points."pc_upgrade_advisor.market_adapters"]
overclockers_uk = "overclockers_uk.adapter:create"
```

Your factory receives the running `Settings` and returns a class that
satisfies `MarketAdapter`. Test it:

```python
from pca.market.plugins import check_conformance
from overclockers_uk.adapter import create

def test_conformance():
    check_conformance(create(settings))
```

Users must opt in to loading plugins:

```bash
PCA_ALLOW_PLUGINS=true pca recommend ...
```

See ADR 0012 for the threat model.

### 8.4 Scrapers

Scraping is **off by default** (ADR 0007). If you enable
`PCA_ENABLE_SCRAPERS=true` you are responsible for the retailer's ToS,
`robots.txt`, and rate limits. Newegg in particular does **not** permit
scraping; use their affiliate feed CSV instead.

---

## 9. LLM "why this upgrade" explainer

The explainer turns an `UpgradePlan` into a plain-English paragraph.
Three backends, selected automatically with fallback:

| Backend            | Location          | Needs                                 |
| ------------------ | ----------------- | ------------------------------------- |
| `DeterministicExplainer` | local template | nothing; always works             |
| `OllamaExplainer`  | localhost LLM     | `ollama serve` on `127.0.0.1:11434`   |
| `OpenAIExplainer`  | OpenAI API        | `OPENAI_API_KEY` + `PCA_ALLOW_CLOUD_LLM=true` |

Privacy: the `ExplainPrompt` is **redacted** before it leaves the
machine - no serial numbers, no MAC addresses, no user paths. Cloud
backends are opt-in and disabled by default.

Use it from Python:

```python
from pca.explainer import explain_plan, ExplainPrompt

resp = explain_plan(ExplainPrompt.from_plan(plan, snapshot=snap))
print(resp.text)
```

A CLI wrapper (`pca explain`) will land once the protocol stabilizes.

---

## 10. Privacy, security, and ToS

- **No telemetry by default.** No crash reports, no usage pings, no
  remote logging. Everything we log is stdout / stderr structlog JSON.
- **No cloud calls by default.** Retailer APIs require credentials you
  provide; cloud LLMs require an explicit flag.
- **No scraping by default.** ADR 0007 - off unless you set
  `PCA_ENABLE_SCRAPERS=true` and own the resulting liability.
- **Plugins are trusted in-process.** ADR 0012 - require
  `PCA_ALLOW_PLUGINS=true`.
- **LAN mode is gated.** Non-loopback `pca serve` requires a
  `--token`. Without one, `pca serve` refuses to bind.
- **Secrets never leave your machine.** `.env` is gitignored; no secret
  is ever written to disk by the app.

---

## 11. Troubleshooting

| Symptom                                            | Likely cause / fix                                                                 |
| -------------------------------------------------- | ---------------------------------------------------------------------------------- |
| `Live inventory is Windows-only in the MVP.`       | You ran `pca inventory` on Linux/macOS without `--stub`. Pass a fixture.           |
| `InventoryError: lshw not available`               | Install `lshw` (`sudo apt-get install lshw`) or run with `--stub`.                 |
| PDF not produced                                   | Install the `reporting` extra **and** the native deps from [§1.1](#11-prerequisites). |
| `FastAPI + uvicorn not installed`                  | `pip install -e ".[web]"`                                                          |
| `non-loopback host requires --token <secret>`      | Provide `--token` when binding to anything other than `127.0.0.1` / `::1`.         |
| Plugin not loaded                                  | Set `PCA_ALLOW_PLUGINS=true`; run `pip show <your-plugin>` to confirm install.     |
| 422 errors from `/api/recommend`                   | Body must be JSON with a non-zero `budget_usd`; check `workload` spelling.         |
| Tax is "$0.00" for a ZIP you expect to tax         | That ZIP may be in a zero-rate state (DE, MT, NH, OR); or unknown and falling back. |
| Chart panel empty in HTML report                   | `matplotlib` is not installed. Install the `reporting` extra.                      |

### Collecting diagnostics

```bash
PCA_LOG_LEVEL=DEBUG pca inventory --stub rig.json 2> pca.log
```

Attach `pca.log` + the snapshot JSON to any issue report. **Do not
attach your `.env`.**

---

## 12. Glossary

| Term                | Meaning                                                                 |
| ------------------- | ----------------------------------------------------------------------- |
| **Snapshot**        | A `SystemSnapshot` - the set of detected components at a point in time. |
| **Catalog score**   | A per-component relative-performance number from the bundled catalog.   |
| **Benchmark score** | A measured score from `pca bench` or a wrapper (fio / sysbench).        |
| **Blended score**   | Benchmark if available (matching env hash), else catalog.               |
| **Workload**        | A weighting preset (gaming / productivity / ML) over component kinds.   |
| **Overall uplift %**| Weighted geometric uplift of the post-upgrade vs. current snapshot.     |
| **Plan**            | Chosen upgrade items under budget + constraints.                        |
| **Quote**           | A plan + tax + shipping + grand total + deal links.                     |
| **KGR**             | Known Good Result - a versioned golden fixture under `tests/data/`.     |
| **ADR**             | Architecture Decision Record under `docs/adr/`.                         |

See also:

- [`docs/architecture.md`](architecture.md) - module map and algorithms.
- [`docs/adr/README.md`](adr/README.md) - all architectural decisions.
- [`docs/data-sources-tos.md`](data-sources-tos.md) - per-retailer stance.
