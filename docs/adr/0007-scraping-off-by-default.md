# 0007 - No scraping without an explicit opt-in

- Status: Accepted
- Date: 2026-04-17
- Tags: legal, market

## Context

Several popular data sources (Newegg catalog, PCPartPicker, boutique sellers)
have explicit ToS clauses forbidding automated access. We could ignore those
clauses to maximise coverage, but that exposes us to cease-and-desist letters
and reputational harm.

Alternatives considered:

- **Opt-out scraping** (on by default, user disables): legally safer than
  nothing but still embeds us in a grey area.
- **Whitelist-only scraping**: ship a curated list of sources we are confident
  allow automated access. Complex to maintain.
- **Opt-in scraping** (chosen): users affirmatively flip a setting before any
  scraping occurs.

## Decision

- Default: `PCA_ENABLE_SCRAPERS=false`. When false, the registry silently
  drops any adapter whose `source_kind` is `scrape`.
- When true, every scrape call:
  - Logs a structured warning including the target URL.
  - Writes an audit entry under `~/.cache/PCUpgradeAdvisor/audit.log`.
  - Enforces >=1s/host rate limit and honours `robots.txt`.
- No scraper may be bundled for a site whose ToS explicitly forbids automated
  access (Newegg, PCPartPicker, Amazon catalogue).

## Consequences

- Positive: default install is legally clean.
- Positive: power users can still enable scrapers for sites they have a
  right to access (e.g., their own company's intranet catalogue).
- Negative: coverage is reduced until we sign partnership agreements or
  adopt a paid aggregator like Keepa.

## Follow-ups

- Tie each scraper to a per-site entry in `docs/data-sources-tos.md`.
- Add a CLI warning banner ("scrapers are enabled") on every command when the
  flag is flipped.
