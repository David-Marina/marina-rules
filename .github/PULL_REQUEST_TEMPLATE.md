## What rule

<!-- one line: market / scope / rule / value / effective_from -->

## Primary source

<!-- URL to the exchange / ministry / depository notice. Paste the exact sentence as `quote` in the YAML. -->

## Verification level you are claiming and why

<!-- verified / single-source / unverified -->

## Checklist
- [ ] one record (or one tightly related group) in this PR
- [ ] `pytest -q` passes locally
- [ ] `python scripts/audit_bars.py data/samples/cn_bars` passes
- [ ] `quote` is verbatim from the source
- [ ] `content_sha256` computed with `python scripts/hash_source.py <url> --quote "..."` (prints FOUND verbatim)
