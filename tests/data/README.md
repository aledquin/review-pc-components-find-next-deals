# `tests/data/` - Known Good Results (KGRs)

Versioned golden fixtures that drive functional tests. **Do not edit these files** unless the expected output genuinely changed - if a test fails, first ask whether the production code is wrong before blessing a new snapshot.

## Layout

- `inventories/` - three reference rigs: `rig_budget.json`, `rig_mid.json`, `rig_highend.json`
- `market_snapshots/` - `snapshot_normal.json` (steady prices), `snapshot_deal_heavy.json` (many active discounts)
- `expected_plans/` - expected `UpgradePlan` per `(rig, budget, snapshot, strategy)` triple
- `expected_quotes/` - expected `Quote` output (includes tax + shipping stubs)
- `expected_reports/` - expected `Report` JSON portion per rig
- `vcr_cassettes/` - replay cassettes for retailer-adapter contract tests

## Stability rules

1. All timestamps are UTC ISO-8601 with `Z` suffix.
2. Money is a string with exactly two decimal places (serialized `Decimal`).
3. Tuples are serialized as JSON arrays (Pydantic default).
4. SKUs follow `{SOURCE}-{MODEL}` to stay unique across adapters.
5. Ties in any ranker resolve by `(source, sku)` ascending to keep golden files deterministic.
