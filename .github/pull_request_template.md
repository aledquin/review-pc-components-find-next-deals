# Pull Request

## What

<!-- One-line summary of the change. -->

## Why

<!-- Link to the issue / roadmap item. -->

## TDD checklist

- [ ] Added or updated **failing test** first (Red).
- [ ] Minimal implementation to pass (Green).
- [ ] Refactored for clarity and kept tests green.
- [ ] Golden fixtures (`tests/data/`) updated **only** when the expected output genuinely changed.
- [ ] `pytest-socket` not disabled in unit tests.
- [ ] Coverage on `src/pca/{budget,gap_analysis,deals,recommender,core}` stays >= 90%.

## Risk / compatibility

<!-- Windows? Linux? macOS? Any retailer ToS implications? -->
