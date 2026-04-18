# 0002 - Pydantic v2 for the domain model

- Status: Accepted
- Date: 2026-04-17
- Tags: domain, validation

## Context

All domain entities (Component, SystemSnapshot, MarketItem, Deal, UpgradePlan,
Quote, Report) serve triple duty: in-memory model, JSON schema for KGRs, and
wire format for the upcoming web dashboard. Hand-rolled dataclasses + ad-hoc
validation will drift against the golden files within weeks.

Alternatives considered:

- **dataclasses + attrs**: ergonomic but no schema export, no validators, no
  JSON round-trip.
- **msgspec**: very fast but the validator ecosystem is immature.
- **Protocol Buffers**: great for RPC but a nuisance for human-readable KGRs.

## Decision

Adopt **Pydantic v2** with `model_config = ConfigDict(frozen=True)` everywhere.
The default `mode="python"` is used for normal calls; schema export feeds the
KGR validators in `tests/units/test_kgr_fixtures.py`.

## Consequences

- Positive: single source of truth for types, validation, and JSON schema.
- Positive: `frozen=True` models are hashable and safe to share across threads.
- Negative: v2's `mypy` plugin is still catching up on some generics; we pin
  versions and accept a small number of `# type: ignore[...]` entries.
- Negative: Pydantic is a heavy dependency (~5MB). Acceptable for a CLI and
  desktop shell, but we keep it out of `core.errors` and `core.logging`.

## Follow-ups

- Auto-generate JSON schema docs under `docs/schemas/` in Wave 2.
- Migrate to `pydantic.dataclasses` for purely-internal helpers once v2.9+
  stabilises the mypy plugin.
