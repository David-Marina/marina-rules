# Contributing to Marina

Marina is a commons. It works only if many people who actually trade in a market keep its rules honest. Thank you for being one of them.

## The one rule

**Every record cites a primary source, and every source is pinned by hash.** A pull request that adds or changes a rule must link the exchange / ministry / depository notice that states the value and the effective date, include the sentence that says so verbatim in `quote`, and include the content hash of the fetched document in `content_sha256` (text hash for HTML, byte hash for PDF — computed by `scripts/hash_source.py`, so CMS re-renders don't break it). Secondary sources (news, wikis, blogs, other repositories) may be added as supporting evidence but cannot by themselves raise a record above `unverified`.

This is enforced by the loader, by the tests, and by CI — a `verified` or `single-source` record with a source lacking `content_sha256` or `quote` makes the whole dataset refuse to load. Reachability of the URL from any particular network is *not* required; the hash is the durable evidence. To compute it:

```bash
python scripts/hash_source.py https://www.szse.cn/... --quote "the sentence you are citing"
```

If you cannot find the primary source, you may still contribute the record at `verification: unverified` with the best secondary sources you have and a clear `notes` field. An honest `unverified` is far more useful than a confident guess.

## What to contribute

- A new rule record (price limit, fee, session, tick/lot, settlement, margin) for any market.
- A source for an existing `unverified` or `single-source` record (this is the most valuable contribution right now).
- A correction, with the source that shows the current record is wrong.
- A violation found by `scripts/audit_bars.py` against your own data, with the example rows.

Please do **not** contribute: constituent lists, ST/suspension lists, prices, adjustment factors, or anything derived from licensed data. See *Scope* in the README.

## How

1. One record (or one closely related group) per pull request. Small PRs get merged; large ones get discussed.
2. Edit the YAML under `data/<market>/`. Follow [`docs/SCHEMA.md`](docs/SCHEMA.md). Ids are stable: `<market>.<family>.<scope>.<effective_from>`.
3. Add the source(s):
   ```yaml
   sources:
     - url: https://www.szse.cn/...
       publisher: SZSE
       title: 深圳证券交易所创业板交易特别规定
       date: 2020-06-12
       kind: official          # official | secondary
       quote: "创业板股票竞价交易实行价格涨跌幅限制，涨跌幅限制比例为20%"
       content_sha256: <REQUIRED — output of scripts/hash_source.py; 64 hex chars>
       hash_kind: text          # text (HTML, extracted) | bytes (PDF/DOCX)
   ```
   `quote` must be text that actually appears in the source. Do not paraphrase inside `quote`.
4. Set `verification` honestly per the table in the README. Maintainers may lower it; they will say why.
5. Run `pytest -q` and `python scripts/audit_bars.py data/samples/cn_bars`. CI runs the same.
6. Open the PR. Describe what the rule is, where you found it, and what it changes for a backtest.

## Review

A maintainer will check the source says what the record says, that the interval does not overlap an existing record of the same key, and that the audit still passes. Expect questions; they are about the source, never about you.

Changes to `verified` records require two maintainer approvals.

## Code of conduct

Be precise and be kind. Disagreements are settled by sources, not by seniority. Harassment of any kind is not tolerated.
