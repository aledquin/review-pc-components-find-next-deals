# 0006 - Retailer adapters via a Protocol + registry

- Status: Accepted
- Date: 2026-04-17
- Tags: market, extensibility

## Context

We need to plug several retailers (Best Buy, Amazon, eBay, Keepa...) into a
common pipeline without letting retailer-specific quirks leak into the
optimizer or reporting layers.

Alternatives considered:

- **Inheritance-based ABC with lots of template methods**: rigid and forces
  retailer quirks into the base class.
- **Plugin entry points (`importlib.metadata`)**: useful for out-of-tree
  plugins, but premature for the MVP.
- **One module per retailer, imported directly**: fast to write, but every
  new adapter requires orchestrator edits.

## Decision

Define `MarketAdapter` as a structural `Protocol` with three methods
(`search`, `get_by_sku`, `list_deals`). Register adapters in an
`AdapterRegistry` keyed by retailer id. The orchestrator queries the registry,
which in turn dispatches to the configured adapters.

```python
class MarketAdapter(Protocol):
    name: str
    def search(self, q: SearchQuery) -> Iterable[MarketItem]: ...
    def get_by_sku(self, sku: str) -> MarketItem | None: ...
    def list_deals(self, skus: Iterable[str]) -> Iterable[Deal]: ...
```

## Consequences

- Positive: retailers are composable; we can A/B price sources trivially.
- Positive: contract tests can iterate the registry and assert every adapter
  satisfies the Protocol against a shared cassette set.
- Negative: Protocol structural typing requires `mypy --strict`; missing
  methods surface late. We offset this with a `AdapterRegistry.validate()`
  hook run in test setup.

## Follow-ups

- Wave 3: load third-party adapters via `pca.market.adapters` entry points.
- Document adapter conformance in `docs/data-sources-tos.md` alongside ToS.
