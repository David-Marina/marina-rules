# Changelog

Every Marina release, newest first. Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

How to read an entry:

- **Dataset** is the first 16 hex of the dataset digest — the `sha256:` in `mr.citation()`. Two results
  that cite the same digest ran against byte-identical rules. The release notes carry the full 64 hex.
- **Corrected (re-run needed)** lists every change `python -m marina_rules.diff <previous> <this>`
  classifies as `correction` (Marina was wrong about the past, or history was re-cut), with its
  interval, plus any behaviour change the diff cannot see. **Added** = `coverage_added` /
  `regime_change`; **Changed** = renames, bookkeeping, metadata, code and docs.
- **Two packages, two kinds of entry.** `## [YYYY.MM.DD]` is a release of the dataset, the
  `marina-rules-data` package; `## [marina-rules X.Y.Z]` is a release of the code, the `marina-rules`
  package. They are released separately: a data release does not need a new code release, and the
  reverse. Entries up to and including 2026.11.13 are from before the split, when one package
  carried both; their version is the data version.
- **Versions are names, not release dates.** The date after each heading is the release date in Asia/Tokyo.
- **Version scheme.** Data: `YYYY.MM.DD`, and `YYYY.MM.DD.N` for a further release on the same day — never a
  letter suffix, which PEP 440 reads as a pre-release (GOVERNANCE.md). Code: semantic versions from
  `1.0.0`. The release workflow refuses any tag that `packaging` reports as a pre/dev release.
- **Compatibility.** A code entry says which data it reads (the oldest data version and the data
  formats); a data entry that needs a newer code release says so.

## [2026.11.13] - 2026-11-13

First release from this repository. The previous release on PyPI is **2026.10.26.5**; everything below is
measured against it. 2026.10.26.6, 2026.10.26.7 and 2026.11.02 were prepared in the previous repository but
never published — their content ships here, and their entries are kept in
[docs/history/CHANGELOG-through-2026.11.02.md](https://github.com/David-Marina/marina-rules/blob/main/docs/history/CHANGELOG-through-2026.11.02.md).

Dataset: `sha256:a66ca0e3fe8e3659` · 2873 records (1421 `verified`, 1451 `single-source`, 1 `unverified`):

| market group | records | `verified` | `single-source` | `unverified` |
|---|---:|---:|---:|---:|
| China A-share (XSHG, XSHE, BJSE) | 146 | 114 | 31 | 1 |
| CFFEX stock-index futures (IF, IH, IC, IM) | 67 | 62 | 5 | 0 |
| CFFEX treasury bond futures (TF, T, TS, TL) | 61 | 53 | 8 | 0 |
| SHFE commodity futures | 1044 | 846 | 198 | 0 |
| INE commodity futures | 281 | 233 | 48 | 0 |
| CZCE commodity futures | 872 | 27 | 845 | 0 |
| GFEX commodity futures | 220 | 66 | 154 | 0 |
| Hong Kong equities (XHKG) | 75 | 6 | 69 | 0 |
| US equities (XNYS, XNAS) | 107 | 14 | 93 | 0 |

`python -m marina_rules.diff <2026.10.26.5 data> <2026.11.13 data>` (88 → 2873 records; 2026.10.26.5 is
`sha256:4b17aa985fe49ae7`) reports **18 `correction`**, 0 `regime_change`, 0 `removed`, **2770 `coverage_added`**,
0 `rename`, 0 `bookkeeping` and **18 `metadata`**. Either argument may be a directory holding the data, e.g. the
`marina_rules/data` directory of the 2026.10.26.5 wheel.

No value that 2026.10.26.5 returned changed: each of its 88 records still gives the same answer for each of its
markets on its first day, last day and every boundary of the new records in its interval. Every correction below
is a date range where 2026.10.26.5 had **no record** (`KeyError` / `OUT_OF_COVERAGE`), or a record extended to
BJSE. What does change for existing calls is listed under *Behaviour*.

### Corrected (re-run needed)
Re-run anything that touched these intervals if you substituted something for the missing rule
(`market / scope / rule [from, to)`; `to` open = still in force):

- `cn.fee.stamp_duty_sell.2005-01-24` — XSHG+XSHE / stock / `stamp_duty_sell` [2005-01-24, 2007-05-30): no record → 0.001.
- `cn.fee.stamp_duty_sell.2007-05-30` — XSHG+XSHE / stock / `stamp_duty_sell` [2007-05-30, 2008-04-24): no record → 0.003.
- `cn.fee.stamp_duty_sell.2008-04-24` — XSHG+XSHE / stock / `stamp_duty_sell` [2008-04-24, 2008-09-19): no record → 0.001.
- `cn.fee.stamp_duty_sell.2008-09-19` — XSHG+XSHE / stock / `stamp_duty_sell` [2008-09-19, 2023-08-28): `effective_to`
  2023-08-28 → 2021-11-15; the same 0.001 continues as the next record. Same value for XSHG and XSHE on every date.
- `cn.fee.stamp_duty_sell.2021-11-15` — XSHG+XSHE+BJSE / stock / `stamp_duty_sell` [2021-11-15, 2023-08-28): 0.001,
  now also for BJSE (no BJSE record before).
- `cn.fee.stamp_duty_sell.2023-08-28` — stock / `stamp_duty_sell` [2023-08-28, open): market XSHG+XSHE → XSHG+XSHE+BJSE
  (0.0005 now also answers for BJSE; the MOF notice is national).
- `cn.fee.transfer_fee_each_side.2022-04-29` — stock / `transfer_fee_each_side` [2022-04-29, open): market XSHG+XSHE →
  XSHG+XSHE+BJSE (0.00001 now also answers for BJSE).
- `cn.fee.transfer_fee_each_side.szse.2006-07-01` — XSHE / stock / `transfer_fee_each_side` [2006-07-01, 2015-08-01):
  no record → 0.0000255 of turnover (inside the SZSE handling fee). SSE charged by par value before 2015-08-01: new rule
  `transfer_fee_par_value`.
- `cn.limit.min_tick.sse.2006-07-01` — XSHG / stock / `limit_price_min_tick` [2006-07-01, 2023-04-10): no record →
  `false` (no one-tick floor). `limit_price()` is unchanged.
- `cn.limit.min_tick.szse.2006-07-01` — XSHE / stock / `limit_price_min_tick` [2006-07-01, 2011-02-28): no record →
  `false`. `limit_price()` is unchanged.
- `cn.settle.etf_money.sse.2013-01-28` — XSHG / etf_money / `min_holding_days` [2013-01-28, 2013-12-09): no record → 1 (T+1).
- `cn.settle.etf_money.szse.2013-11-30` — XSHE / etf_money / `min_holding_days` [2013-11-30, 2013-12-09): no record → 0.
- `cn.settle.etf_money.2013-12-09` — XSHG+XSHE / etf_money / `min_holding_days` [2013-12-09, 2015-01-19): no record → 0.
- `cn.settle.etf_bond.sse.2013-03-15` — XSHG / etf_bond / `min_holding_days` [2013-03-15, 2013-08-05): no record → 0.
- `cn.settle.etf_bond.2013-08-05` — XSHG+XSHE / etf_bond / `min_holding_days` [2013-08-05, 2015-01-19): no record → 0.
- `cn.settle.etf_gold.sse.2013-07-27` — XSHG / etf_gold / `min_holding_days` [2013-07-27, 2013-11-30): no record → 0.
- `cn.settle.etf_gold.2013-11-30` — XSHG+XSHE / etf_gold / `min_holding_days` [2013-11-30, 2015-01-19): no record → 0.
- `cn.limit.delisting_day1.szse.2020-08-24` — XSHE / delisting_day1 / `price_limit_pct` [2020-08-24, 2020-12-31): no
  record → 0.1, main board only. ChiNext stocks in that window use the new scopes `delisting_chinext_pre0824` (10%) /
  `delisting_chinext_post0824` (20%), selected by context key `delisting_entry_before_2020_08_24` (深证上〔2020〕620号).

**Behaviour** (invisible to the diff — code, registry or new records that change an existing call):

- **Convertible tick.** `tick_size('convertible' | 'convertible_day1', …)` used to fall through to the stock tick 0.01.
  Convertibles now have their own records: 0.001 on both exchanges from 2022-08-01; SSE 0.01 before; SZSE 0.01 from
  2006-07-01, 0.001 from 2011-02-28 (2011-02-28 → 2012-12-10 is `unverified`: two official SZSE texts disagree, so
  `resolve` refuses it at the default `min_verification`). `limit_price` on convertibles from 2022-08-01 now rounds to
  0.001 (prev close 100.003 → 120.004 / 80.002; was 120.00 / 80.00), and `marina check` flags off-tick convertible
  prices. **Re-run** convertible results from 2022-08-01 that used `limit_price` or the tick.
- **Contradictory or null context → `MISSING_CONTEXT`.** Scopes now carry declarative `asserts` (`data/cn/scopes.yaml`,
  published in `capabilities.json`): the board must match the scope, ordinary boards exclude the IPO window, IPO scopes
  require their day range and issue regime, `etf_20pct` requires all-20%-band constituents, convertible day 1 vs later,
  delisting / REIT day 1 vs later, `bse` not ST, and a key passed as `null` counts as missing; cross-border funds under
  `etf` require `underlying_t0`. Such calls returned `DETERMINED` before.
- **Lookups without a market.** `rule_at` / `record_at` with `market=None` now raise `RuleConflict` where
  per-exchange records are in force: `limit_price_min_tick` / stock from 2011-02-28 (SSE `false` vs SZSE `true`
  until 2023-04-10, then a separate `true` record per exchange) and `price_limit_pct` / delisting_day1
  2020-08-24 → 2020-12-31 (SSE vs SZSE). Pass `market=`; no answer with a market changed.
  `limit_price(…, market=None)` now succeeds when every in-force tick agrees.
- **`marina check`.** New finding `PRICE_OFF_TICK`; a non-finite price or prev_close is `ROW_INVALID` also for unlimited
  scopes; the statutory fee floor uses the fill's side (`stamp_duty_buy` for buys) and market; Hong Kong and US rows are
  `MARKET_UNSUPPORTED`. The stamp now commits to every column a check uses (canonical form `marina-check-canon/2`):
  **stamps issued by 2026.10.26.5 are not comparable — recompute them.**
- `scripts/audit_bars.py` picks the IPO regime from each board's switch date (main board 2023-04-10, ChiNext
  2020-08-24): results for main-board listings 2023-02-17 … 2023-04-09 and ChiNext / STAR listing windows changed.
- `record_at` / `coverage` treat records whose market sets intersect (`XSHG+XSHE` vs `XSHE`) as overlapping (exact
  string comparison before). The data has no such overlap.

### Added
2770 records with no counterpart in 2026.10.26.5:

- **China A-share**, 43: sessions for BJSE, convertibles and REITs; convertible and BJSE ticks; BJSE T+1, convertible
  same-day rotation and REIT T+1; buy-side stamp duty (bilateral 2005-01-24 → 2008-09-19, 0 after); the SSE par-value
  transfer fee before 2015-08-01 and the BJSE transfer fee 2021-11-15 → 2022-04-29; commission cap / minimum for funds,
  REITs and convertibles (SSE 2006-07-01 → 2021-12-31, SZSE 2006-12-30 → 2014-08-25); the ChiNext delisting split
  (2 records); the SSE STAR growth-tier risk disclosure requirement from 2025-07-13 (new rule
  `retail_risk_disclosure_required`, 2 records).
- **CFFEX stock-index futures** (IF, IH, IC, IM), 67: margin, trading / close-today / delivery fees, daily price limits,
  sessions and same-day round trips.
- **CFFEX treasury bond futures** (TF, T, TS, TL), 61: price limits, margin, sessions, per-lot trading and delivery
  fees, same-day round trips, each from its listing day (TF 2013-09-06).
- **SHFE**, 1044: 20 products (CU, AL, ZN, PB, NI, SN, AO, AD, AU, AG, RB, WR, HC, SS, FU, BU, RU, SP, BR, OP) —
  speculative margin, daily price limits, sessions with night session, same-day round trips and exchange trading /
  close-today fees, from 2024-01-01 (AD, OP from listing).
- **INE**, 281: SC, LU, NR, BC, EC — the same rules and fees, from 2024-01-01 (EC from listing 2023-08-18).
- **CZCE**, 872: 27 products — speculative margin, daily price limits, same-day round trips and exchange fees from
  2024-01-01; sessions for PF and PR only; most values from the daily settlement-parameter file alone (`single-source`).
- **GFEX**, 220: SI, LC, PS, PT, PD — speculative margin, daily price limits, same-day round trips and exchange fees
  from 2024-01-01 (PS from 2024-12-26, PT and PD from 2025-11-27); no sessions yet.
- **Hong Kong** (XHKG shares and ETFs), 75: stamp duty, SFC / AFRC levies, trading fee and tariff, settlement fee,
  Investor Compensation levy (suspended: 0), no daily limit (`unlimited`), sessions (shares), same-day resale, T+2,
  spread tables, pre-opening and closing-auction price limits, VCM triggers, the short-selling tick rule, the
  quotation spread limit and the order-price multiple check.
- **US equities** (XNYS, XNAS stocks and ETFs), 107: SEC Section 31 fee, FINRA TAF, settlement cycle, same-day resale,
  Rule 612 increment, LULD bands, market-wide circuit-breaker levels, 2011–2013 single-stock pause thresholds, CAT fee
  and historical assessment, Regulation SHO price test, pattern-day-trader minimum, sessions per primary listing
  exchange and Nasdaq extended hours. No daily price limit (a known gap).
- Where values differ by contract, or a period could not be pinned to one product-level value, the interval is a
  **known gap** with an id instead of a guess.

New rules: `margin_ratio`, `price_limit_pct_of_prev_settlement`, `trans_fee_rate`, `trans_fee_per_lot`,
`close_today_fee_rate`, `close_today_fee_per_lot`, `delivery_fee_rate`, `delivery_fee_per_lot`, `stamp_duty_buy`,
`transfer_fee_par_value`, `retail_risk_disclosure_required`, `transaction_levy_each_side`, `afrc_levy_each_side`,
`investor_compensation_levy_each_side`, `trading_fee_each_side`, `trading_tariff_per_trade`, `settlement_fee_each_side`,
`settlement_cycle_days`, `tick_size_table`, `opening_auction_limit_pct`, `closing_auction_limit_pct`, `vcm_trigger_pct`,
`short_sale_price_test`, `order_spread_limit`, `order_price_multiple_limit`, `sec_fee_rate_sell`, `finra_taf_sell`,
`cat_fee_per_share`, `cat_historical_assessment_per_share`, `min_quote_increment`, `luld_band`, `mwcb_decline_levels`,
`single_stock_pause_pct`, `pattern_day_trader_min_equity`, `extended_hours` (definitions in docs/SCHEMA.md).

### Changed
- **Metadata** (18 records, no value or date changed): 5 raised `single-source` → `verified` (SZSE commodity-futures ETF
  T+1 / T+0, SSE B-share tick, SZSE REIT bands); 8 `published_at` dates found; sources and notes on the rest.
- **Schema 1.2 — futures contract selectors.** A record or known gap may carry `contracts: {any | none: [clause]}`
  (`code`, `delivery_month`, `months_to_delivery`); files that use it declare `schema: 1.2`. `record_at` / `rule_at` /
  `coverage` take `contract=`, `resolve` reads `context["contract"]`; where values differ by contract and none is
  given: `ContractRequired` (a `KeyError`) / `MISSING_CONTEXT` (`contract`). Without a selector a record covers every
  contract, as before; 1.1 files load unchanged.
- **Per-market data directories.** `data/cn/`, `data/hk/`, `data/us/`, each with its own `scopes.yaml` and
  `known_gaps.yaml`. `coverage()`, `gaps_for()` and `contract.resolve()` pick the registry from the market
  (`market_prefix_for`: `hk` for XHKG, `us` for XNYS / XNAS, `cn` otherwise), so China answers are unchanged. Gap ids
  may carry a market namespace (`G-HK-0001`, `G-US-0001`). New `capabilities-hk.json` and `capabilities-us.json`
  (`python -m marina_rules.contract --capabilities hk` / `us`); the release JSON / SQLite export covers all three.
- **New context keys**: `contract` (futures), `star_growth_tier`, `delisting_entry_before_2020_08_24`, `spread_table`
  (Hong Kong ETFs).
- **`as_of`** (bitemporal) on `record_at`, `rule_at`, `coverage`, `contract.resolve`, `limit_price`, `tick_size`,
  `min_tick_band` and the CLI (`--as-of`): answer only from rules published on or before that date. New statuses
  `NOT_YET_PUBLISHED` and `UNKNOWN_PUBLICATION` (decision schema and capabilities). `as_of=None` behaves as before.
- `session_schedule` gains optional keys `night` and `day_call`; the loader validates band tables, LULD tiers,
  trading-pause groups, short-sale tests, order-entry checks and fee fractions (docs/SCHEMA.md).
- **Dataset digest** walks the data files in relative-path order across directories (with several market directories the
  order came from the filesystem before). The digest of a one-directory dataset such as 2026.10.26.5 is unchanged.
- Coverage targets for China A-shares (`coverage/cn_targets.yaml`, `scripts/coverage_report.py`): 137 targets, 97.25%
  of target-days from 2006-07-01; CI fails on any gap not listed as `unresolved`.
- Conformance vectors: 559 (166 in 2026.10.26.5).
- Project home and the decision schema's `$id` moved to this repository.
- **CI no longer fetches source pages.** The check that requested every source URL of every record on each push was
  removed: at 2873 records it would send several thousand requests to exchange websites per run. Sources are
  verified when a record enters (content hash and quote, enforced at load); page changes are watched by the weekly
  `scripts/source_watch.py` run.

### Method
Candidate records were researched with automated agents. Before entry the maintainer re-fetched every source,
recomputed its content hash and checked every quote against the fetched text.

## Earlier releases

Releases up to 2026.11.02 (and the never-published 2026.10.26.6 and 2026.10.26.7) are recorded in
[docs/history/CHANGELOG-through-2026.11.02.md](docs/history/CHANGELOG-through-2026.11.02.md).
