# Conformance vectors

Inputs and expected outputs for anyone who wants to check that *their* implementation — in any
language, with or without Marina's code — agrees with the Chinese A-share rule history as the
exchanges published it.

**Where the expected values come from.** Every vector carries an `oracle`: the primary text or the
arithmetic (quoted) that fixes the expected value, reviewed by a person. They were **not** produced
by running Marina and copying the output; Marina is one implementation under test here, and
`tests/test_conformance.py` is where it is tested. If a vector and Marina disagree, the vector wins
until someone shows the oracle was misread.

**Shape.** `vectors/*.json`, one file per theme, each a list of objects:

```json
{"id": "LIM-0007", "query": {"rule": "price_limit_pct", "trade_date": "2020-08-24", "scope": "chinext", "market": "XSHE",
                             "context": {"board": "chinext", "st_status": false, "listing_day_index": 900}},
 "expect": {"status": "DETERMINED", "value": 0.2},
 "oracle": "深证上〔2020〕620号《创业板交易特别规定》2.1：涨跌幅限制比例为20%；2020-08-21 发布会：8月24日起施行",
 "tags": ["regime-switch", "first-day-of-new-rule"]}
```

Only the keys present in `expect` are compared (`status`, `value`, `missing_context`, `known_gap_ids`, `tracking`,
`warnings`), so a decision key added later never breaks an existing vector. `query.require_tracked: true` passes the
opt-in that refuses carry-forwards (`vectors/tracking.json`; the oracle there is the tracking registry entry plus the
record's interval).

For `limit_price` vectors `query.prev_close` is set and `expect.limit_up` / `expect.limit_down` are the
expected prices; the oracle quotes the exchange's formula and rounding rule.

**Coverage of this first batch (103 vectors):** every regime switch one day before and on the day;
ST vs non-ST on both main board bands; IPO first-5 / listing-day scopes under both regimes; STAR /
ChiNext / BSE; one-tick floor on both exchanges around their adoption dates; funds and convertibles;
fees at each change; missing and contradictory context; known gaps and blind spots; the
verification bar. Themes not yet covered (sessions, T+1, delisting period, REITs) are known gaps
and appear as `OUT_OF_COVERAGE` vectors with their `known_gap_ids`.

**Versioning.** Vectors pin `ruleset_version_min`: the first Marina release whose data they describe.
A later release that changes an expected value must either be a documented correction (see
`diff_rules`) or a bug in the vector; either way the vector file changes in the same PR.
