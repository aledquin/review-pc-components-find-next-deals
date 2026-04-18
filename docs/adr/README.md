# Architecture Decision Records

We use lightweight Markdown ADRs, one per decision, named
`NNNN-title-with-dashes.md`. The first digit group is a zero-padded sequence.
Status is one of `Proposed`, `Accepted`, `Deprecated`, or `Superseded by NNNN`.

## Index

- [0001 - Python 3.12+ as the single runtime](0001-python-3.12-runtime.md)
- [0002 - Pydantic v2 for the domain model](0002-pydantic-v2-domain-model.md)
- [0003 - Two optimizers: greedy + PuLP ILP](0003-two-budget-optimizers.md)
- [0004 - Strict TDD with pytest-socket](0004-tdd-pytest-socket.md)
- [0005 - CLI-first UX roadmap](0005-cli-first-ui-roadmap.md)
- [0006 - Retailer adapters via a Protocol + registry](0006-market-adapter-registry.md)
- [0007 - No scraping without an explicit opt-in](0007-scraping-off-by-default.md)

## Template

```markdown
# NNNN - Short Decision Title

- Status: Proposed | Accepted | Deprecated | Superseded by NNNN
- Date: YYYY-MM-DD
- Deciders: @your-handle
- Tags: tag1, tag2

## Context

## Decision

## Consequences (positive / negative)

## Alternatives considered
```
