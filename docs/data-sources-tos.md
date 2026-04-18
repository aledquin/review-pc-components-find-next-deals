# Data Sources & Terms-of-Service Stance

This document tracks every external data source the project can talk to, how we
authenticate, how often we may call it, and the legal posture we take. It is
intentionally conservative: if in doubt, we disable the integration.

Maintainers: update this table whenever you add, remove, or change an adapter.

## Status legend

- **Shipped** - adapter is implemented and covered by contract tests.
- **Stubbed** - adapter skeleton + cassette exists; live calls disabled.
- **Proposed** - not implemented; listed for roadmap.

## Source matrix

| Source                | Kind        | Auth                               | Rate limits (public)                          | ToS stance                                  | Caching                                  | Status    |
| --------------------- | ----------- | ---------------------------------- | --------------------------------------------- | ------------------------------------------- | ---------------------------------------- | --------- |
| Best Buy Developer    | REST API    | API key (`PCA_BESTBUY_API_KEY`)    | 5 req/s, 50k/day (key-scoped)                 | Use allowed for price comparison apps.       | 24h TTL on `/products`, 1h on stock.     | Shipped   |
| Amazon PA-API 5       | REST API    | Associate tag + signed request      | 1 TPS base; grows with sales; 8,640/day cap.   | Must be an Associate, must show disclosure.  | 1h TTL, respect `ItemLookup` quotas.     | Shipped   |
| eBay Browse API       | REST API    | OAuth2 (client credentials)         | 5k/day per app (sandbox), 5M/day production.  | Allowed for price comparison.                | 1h TTL.                                  | Proposed  |
| Newegg Marketplace    | REST API    | Seller API only                    | N/A (no public catalog API).                   | Scraping prohibited by ToS.                  | n/a                                      | Proposed  |
| PCPartPicker          | HTML        | None                                | Unofficial; site actively blocks scrapers.     | Scraping prohibited by ToS.                  | n/a                                      | Disabled  |
| Keepa                 | REST API    | API key (`PCA_KEEPA_API_KEY`)      | Token-bucket; depends on subscription tier.    | Paid service; redistribution restricted.     | 24h TTL.                                 | Proposed  |
| Geizhals (EU)         | REST + HTML | API key (partner) / HTML            | Partner-only API; HTML scraping gray-area.     | EU-only, out of scope for US-first MVP.      | n/a                                      | Deferred  |
| Manufacturer BIOS/driver feeds | Mixed | Varies                             | Varies.                                        | Usually allowed for product support tools.   | 24h TTL.                                 | Proposed  |

## Scraping posture

- **Default off.** `PCA_ENABLE_SCRAPERS=false` is the shipped default. Turning
  it on emits a structured warning and records an audit log entry per run.
- Scrapers MUST:
  - Honour `robots.txt` (we use the `robotexclusionrulesparser` strategy).
  - Send a descriptive `User-Agent` referencing this project.
  - Rate-limit to <=1 request/sec/host unless the host publishes a higher
    allowance.
  - Short-circuit on any HTTP 429/5xx with exponential backoff + jitter.
  - Cache responses for at least 1h to reduce load.
- Any retailer whose ToS explicitly forbids scraping (Newegg, PCPartPicker,
  most boutique sellers) is permanently excluded unless we obtain written
  partnership.

## Regional scope (MVP)

- **US** locale, **USD** currency, **imperial** units where the plan asks for
  them (chassis clearance inches alongside mm).
- International retailers appear only behind `PCA_REGION!=us` which is not
  currently exposed; EU/UK/APAC land in Wave 3.

## Privacy

- No user-identifying telemetry leaves the machine.
- Market queries **do** leak queried SKUs to the retailer (unavoidable).
- When we ship the optional community benchmark database (stretch goal), it is
  strictly opt-in, stripped of serials, and submitted over TLS with a
  per-install pseudonymous ID the user may rotate.

## Legal hygiene

- Each shipped adapter links to its current ToS in its module docstring.
- `scripts/licensecheck.sh` (Wave 2) will fail the build if any dependency
  carries a GPL license incompatible with the project's Apache-2.0 licence.
- A third-party notices file (`NOTICES.md`) will be generated during release.

## Revisiting this document

- Review cadence: quarterly, and any time a retailer changes its ToS.
- All changes go through a pull request and reference the ADR that touches the
  affected adapter.
