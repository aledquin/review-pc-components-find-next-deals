# 0012 - Retailer plugin SDK via `importlib.metadata` entry points

- Status: Accepted
- Date: 2026-04-17
- Deciders: @pca-team
- Tags: market, plugins, v1.x

## Context

First-party retailer coverage is forever incomplete. Regional retailers
(Overclockers UK, PCComponentes ES, Scorptec AU) and niche used-market
sites (r/hardwareswap archive mirrors) deserve a stable extension point.

## Decision

Third-party plugins register a `MarketAdapter` factory under the
`pc_upgrade_advisor.market_adapters` entry-point group. `load_plugin_adapters`
discovers all installed plugins, invokes the factory with the running
`Settings`, and validates the returned adapter's public surface.

Plugin authors run `check_conformance(adapter)` in their own tests. That
helper exercises every method on the protocol with inputs guaranteed not
to match anything (nonsense SKUs, empty queries) so the conformance suite
is safe to run offline.

Threat model:

- Plugins run in-process. We do **not** sandbox them. Plugin installation
  implies trust - the CLI prints a warning the first time a new plugin is
  detected and requires `PCA_ALLOW_PLUGINS=true` to load them at all.
- Plugins cannot override first-party adapters; registry lookup by `name`
  is first-write-wins.

## Consequences

Positive:

- Zero changes to core code to add a new retailer.
- Per-plugin CI/CD owned by the plugin author.
- Conformance test gives authors a red/green signal without running the
  whole PCA integration suite.

Negative:

- In-process plugins are a supply-chain attack vector. We compensate with
  the opt-in flag, ADR 0007's scraping gate, and explicit warnings on first
  load. A future ADR (0013) should cover WASM sandboxing if plugin
  distribution becomes mainstream.

## Alternatives considered

- **Subprocess plugins (gRPC)**: better isolation, substantially harder DX.
- **WASM plugins (wasmtime)**: strong sandbox, but the Python ecosystem
  tooling is not ready for a market adapter surface with HTTP access.
- **Monolithic repo**: limits contributor velocity and blocks proprietary
  retailers that can't open-source their integrations.
