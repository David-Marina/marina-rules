# Changelog

Every Marina release, newest first. Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

How to read an entry:

- **Dataset** is the first 16 hex of the dataset digest — the `sha256:` in `mr.citation()`. Two results
  that cite the same digest ran against byte-identical rules. The release notes carry the full 64 hex.
- **Corrected (re-run needed)** lists every change `python -m marina_rules.diff <previous> <this>`
  classifies as `correction` (Marina was wrong about the past, or history was re-cut), with its
  interval, plus any behaviour change the diff cannot see. **Added** = `coverage_added` /
  `regime_change`; **Changed** = renames, bookkeeping, metadata, code and docs.
- **Two packages, two kinds of entry.** `## [YYYY.MM.DD]` is a release of `marina-rules`, the package
  you install and upgrade (`pip install -U marina-rules`): the dataset. `## [marina-rules-core X.Y.Z]`
  is a release of the code, `marina-rules-core`, which `marina-rules` depends on. They are released
  separately: a data release does not need a new code release, and the reverse; a data release that
  needs newer code says so and requires it. Entries up to and including 2026.11.16 are from before
  the split, when `marina-rules` carried the code too; their version names both.
- **Versions are names, not release dates.** The date after each heading is the release date in Asia/Tokyo.
- **Version scheme.** Data: `YYYY.MM.DD`, and `YYYY.MM.DD.N` for a further release on the same day — never a
  letter suffix, which PEP 440 reads as a pre-release (GOVERNANCE.md). Code: semantic versions from
  `1.0.0`. The release workflow refuses any tag that `packaging` reports as a pre/dev release.
- **Compatibility.** A code entry says which data it reads (the oldest data version and the data
  formats); a data entry that needs a newer code release says so.

## [Unreleased]

### Corrected (re-run needed)

`marina-check` / `check_rows` issued a `rules-verified` stamp in cases where it should have withheld it. Three were
reported by an outside tester; an independent review of the fix found more of the same kind. All of them are present
in 2026.11.13 and 2026.11.16. The principle behind every item: a changed standard, inputs that contradict each
other, and input that cannot be read never get the stamp a complete, valid check gets. **Re-run** any log those
releases stamped; a stamp from them is not evidence of compliance where one of the cases below applies.

*The standard of the check*

- **A `decimals` cell replaced the exchange's tick and the run was still stamped.** `price=10.001` on a main-board
  stock is `PRICE_OFF_TICK`; with `decimals=3` in the row it passed, stamped. A `decimals` cell now counts as the
  exchange's grid only when 10^-decimals equals the tick recorded for the row's scope, date and market — or, for an
  A-share stock on a date before its first tick record, equals 0.01, the grid the limit prices are rounded at in
  that case. Any other value (finer, coarser, given where the tick differs by exchange and the row names no market,
  or given for a fund, B share or convertible bond that has no usable tick record on that date) is still used
  for the row's checks, but makes the run relaxed: `rules_verified` false, no stamp, `stamp_withheld` says why, and
  the new `decimals_override` counts such rows (`row_status` marks them). A `decimals` that is not an integer from 0
  to 8 is `ROW_INVALID` (a large value used to raise `OverflowError`).
- **Rows whose price grid was not checked looked the same as rows where it was.** Where no tick is recorded for a
  row (dates before 2006-07-01; in a strict run also the SZSE convertible-bond tick of 2011-02-28 to 2012-12-10,
  whose record is `unverified`), the tick check is skipped. The output now says so: `tick_check` counts
  `rows_checked` and `rows_not_checked` (`row_status` marks the latter `tick_not_checked`), and a stamp says nothing
  about the price grid of those rows.
- **`limit_price` rounded funds and B shares at 0.01 where it had no tick for them.** With no `tick_size` in force
  and no `decimals` given, the limit prices were rounded at 0.01 for every instrument. That substitution is
  documented for A-share stocks only (known gap G-0005: their tick before 2006-07-01 is not sourced, and 0.01 is
  the only value it ever had); for scopes `etf`, `b_share` and `st_b_share` on dates before 2006-07-01 — whose
  bands are recorded from 1996 / 1998 and whose ticks were 0.001 or differed by exchange — it produced limit
  prices on the wrong grid, and `marina-check` judged and stamped such rows against them.
  `limit_price(1.234, "etf", "2006-06-30", "XSHG")` returned `(1.36, 1.11)`; it now raises `KeyError`, which names
  the instrument family and the dates that do have a record (the command line and the MCP tool report "not
  answered"; `marina-check` reports `RULE_MISSING` for the row, so the log is not verified). Pass `decimals` only
  if you know the grid the exchange used — in `marina-check` that makes the run relaxed. The 0.01 substitution now
  applies to an A-share stock scope on a date for which the dataset has no stock tick record at all, and to
  nothing else; results for dates from 2006-07-01 are unchanged. **Re-run** anything that took fund or B-share
  limit prices before 2006-07-01 from Marina.

*Inputs that contradict each other*

- **An explicit `scope` overrode what the row itself said about the instrument.** A row with `scope=main_board` and
  `st_status=true` was checked against the ordinary 10 % band and stamped, although `resolve()` refuses the same
  context. A row that names a scope is now compared with that scope's `asserts` in the registry, using the context
  cells the row supplies (every key a scope requires or asserts, the fund keys such as `fund_constituents`
  included), `list_date` where it decides the listing-day index, and the board of a recognised A-share stock code
  when the row has no `board` cell (`scope=ipo_first5_main` on a ChiNext code). A contradiction is the new finding
  `SCOPE_CONTEXT_CONFLICT` and no other check runs on the row. A key the row leaves out is not demanded.
- **Two cells of one row that state different things.** Columns `st` and `st_status` with different values (the
  later column used to win); a `market` or `board` cell that names another exchange or board than a recognised
  stock code (`600000` with `market=XSHE`), or another exchange than a 900… / 200… B-share code; a trade dated
  before its own `list_date`. All are `ROW_INVALID`.
- **Rows of one code on one day that disagree** on the previous close, the scope or the market: the later row gets
  the new finding `ROWS_DISAGREE`.

*Input that cannot be read*

- **An unreadable `fee` or `turnover` skipped the fee check.** `fee=0` is `FEE_BELOW_STATUTORY`, but `fee=nan`,
  `inf` or any text was read as "no fee given" and passed, stamped; so did `turnover=nan`. A cell that is present
  but not a finite number (and a negative turnover) is now `ROW_INVALID`. The adapter (`--format`,
  `marina-rules adapt`) used to drop such a cell before the checker saw it; it now passes an unreadable fee,
  turnover, ST or listing-date cell through as written and counts it under `cells_not_read`. An absent cell still
  means no fee check, and the output now says so: `fee_check` counts `rows_checked` and `rows_not_checked`, and a
  stamp says nothing about the fees of the latter.
- A `price` or `prev_close` that is zero or negative (a zero price against a zero previous close used to pass), an
  empty `code`, a `list_date` that is not a date, and a `date` with anything but a time after the day
  (`2024-03-01XYZ`) are `ROW_INVALID`.
- `marina-check FILLS.csv` refuses a header that names a column twice (exit code 2): the second `fee` column
  silently replaced the first.

Stamps of logs that none of the above touches are unchanged: the canonical form and its version are the same.

**Not changed, so that it is not mistaken for checked:** `turnover` is not reconciled with price × quantity (the
checker reads no quantity); a column the checker does not read (`ST`, `is_st`, `Fee` — names are case-sensitive) is
ignored, and is now listed in `columns_not_read`; a non-strict run (`strict=False`, the command line's default
without `--strict`) can still be stamped, with a stamp that differs from the strict one.

### Changed

- A trade dated on its `list_date` is listing day 1 (`listing_index_from_list_date` returns 1): with
  `issue_regime` given, such a row gets its listing-day scope instead of `SCOPE_UNDETERMINED`.
- `fee_check` counts a row as checked only when the statutory floor for its date was found; `tracking` counts only
  rows the checks ran on. A B-share row without a market is `MARKET_REQUIRED` instead of an uncaught `RuleConflict`.

## [2026.11.16] - 2026-11-16

**In three lines.** *Rules:* none changed — no record's value or interval differs from 2026.11.13.
*Corrections:* two defects in the code of 2026.11.13 returned wrong answers for some calls; see "Corrected" for
what to re-run. *Compatibility:* additive (new functions, options and output keys), except that a query date not written
`YYYY-MM-DD` now raises instead of answering, `tick_size` refuses where it used to answer for instruments without a
tick record, and one refusal changed status (below).

Dataset: `sha256:80188ec249ce22ae` · 2873 records (1421 `verified`, 1451 `single-source`, 1 `unverified`), the
same records as 2026.11.13; two bookkeeping edits (under "Changed") moved the digest.

### Corrected (re-run needed)
No record was corrected. `python -m marina_rules.diff 2026.11.13 2026.11.16` lists one metadata change.

**Behaviour** (invisible to the diff — code that changes an existing call):

- **A date not written `YYYY-MM-DD` selected the wrong rule.** Dates were compared as text without being checked,
  so `"20200102"`, `"2020/01/02"`, `"2020-1-2"`, an integer, `None` or any other string was not refused: it sorted
  after every ISO date of its year and was answered with a later interval — in practice the newest rule.
  `rule_at("price_limit_pct", "20200102", "chinext", "XSHE")` returned 0.2 for a day on which the band was 0.1;
  `limit_price`, `tick_size`, `coverage`, `resolve` (status `DETERMINED`) and `marina-check` behaved the same way.
  Every entry point now accepts an ISO `YYYY-MM-DD` string (a time may follow), a `date` / `datetime`, or an object
  whose `str()` is one, and raises `ValueError` for anything else, naming the ISO form; `marina-check` reports such
  a row as `ROW_INVALID`; the command line exits 2. **Re-run** anything computed with 2026.11.13 or an earlier
  release from dates in another spelling — `YYYYMMDD`, the usual data-vendor format, above all.
- **`tick_size` answered 0.01 for instruments that have no tick record.** A scope outside the tick-family table
  fell back to the A-share `stock` family, so a futures, Hong Kong or US scope asked without a market got the
  A-share tick: `resolve("tick_size", d, "cffex_if")` was `DETERMINED` 0.01, `coverage(None, "cffex_if",
  ["tick_size"], …)` was `complete`, `tick_size("hk_stock" | "us_stock", d)` returned 0.01. The fallback now applies
  to mainland securities scopes only; the others are refused (`KeyError` / `OUT_OF_COVERAGE`). With a market given
  the answer was already a refusal. **Re-run** anything that took a tick from Marina for a futures, Hong Kong or US
  scope.
- **A rule the scope does not hold is `OUT_OF_COVERAGE` even when context is missing** (was `MISSING_CONTEXT`, a
  request for context that could never help): `resolve("price_limit", d, "chinext", "XSHE")`.
- **`rule_at("tick_size", d, <board scope>)` answers** with the tick of the scope's instrument family, as
  `tick_size()` and `resolve()` already did (it raised `KeyError` and pointed to scope `stock`). `record_at` still
  reads exactly the scope it is given.

### Added
- **Tracking registry** (`data/<prefix>/tracking.yaml`): the last date for which each market's official sources
  were checked for rule changes. `tracked_through(market, scope)`, `tracking_registry()`; every decision carries
  `tracking {tracked_through, beyond}` and, for an open-ended record asked beyond that date, a `warnings` entry
  (`CARRY_FORWARD_BEYOND_TRACKED` / `CARRY_FORWARD_UNTRACKED`); `require_tracked=True` refuses such an answer
  (`BEYOND_TRACKING`, `BeyondTracking`). `marina-check` counts the rows it affects. Not part of the dataset digest.
- **Finding out what can be asked.** `rules_for(scope, market)`, `markets_recorded(scope)`; a refusal says what
  exists instead — the `KeyError` text and the new optional decision key `alternatives` (`scope_rules`,
  `similar_rules`, `rule_intervals`, `similar_scopes`, `markets`): names only, never a value. A market code the
  dataset does not use (`SZSE`, `SSE`) is named as such.
- **Statutory fees of a fill**: `statutory_fee_floor(turnover, side, date, market)` and
  `statutory_fee_components(...)` (per rule, with record ids).
- **One command line**, `marina-rules` (= `python -m marina_rules`): `query`, `rules`, `scopes`, `fees`, `check`,
  `adapt`, `mcp`, `capabilities`, `schema`, `skill`, `version`. `SKILL.md` ships in the wheel (`marina_rules.skill_text()`).
- **`marina-check`**: `--no-tick`, `--band-tolerance-pct`, `--assume-seasoned` (relaxed runs: no stamp), `--rows`,
  `--top-codes`; the scope may be left empty and chosen from `board`, `st`, `listing_day_index` / `list_date`
  (`board_for_code` fills the board from the code); optional `day_high` / `day_low` add `PRICE_OUTSIDE_DAY_RANGE`;
  `hints` for price-basis mismatches; `summary` by scope, year, side and code.
- **MCP server** for AI assistants: `pip install "marina-rules[mcp]"` (Python 3.10+), then `marina-rules-mcp` (or
  `marina-rules mcp`). Read-only tools `resolve`, `limit_price`, `statutory_fees`, `coverage`, `list_scopes`,
  `list_rules`, `check_fills`, `citation`; every answer carries the citation, and a refusal is returned as an error
  that says what to ask instead. Nothing changes for code that does not use it.
- **Engine exports** — `marina-rules adapt`, and `marina-check FILE --format NAME`: reads the trades of RQAlpha,
  vn.py, backtrader, 掘金 gm or any table with common column names (`generic`; `--map`, `--side-values`,
  `--side-from-sign`, `--date-format`), and joins what an engine does not export — previous close, day high / low,
  ST status, listing dates — from tables in the layout of Tushare, baostock or RQData (`--bars`, `--st`,
  `--listing`). Each format is a declared reading of named columns and states what it rests on (`--list-formats`);
  no row is dropped and nothing is computed or guessed. The formats were written from the engines' source code and
  the vendors' documentation; they have not yet been run against exports from a live installation of each engine.
  `marina-check` gains `--assume-not-st` (a row without ST information is taken as not ST when its scope cannot be
  chosen otherwise; a relaxed run, no stamp); its output gains `assumed_not_st`, `options.assume_not_st` and, for an
  adapted run, `adapter`.
- **Faster first load.** The wheel carries a precompiled copy of the dataset (`data/compiled.json`), so the first
  `records()` call no longer parses YAML: about 3 s before, about 0.03 s now (one machine, Python 3.12). The copy is
  used only when it matches the YAML beside it and the loader that wrote it; otherwise the YAML is loaded as before,
  with a warning. A source checkout always reads the YAML.
- **`README.zh-CN.md`**, a Chinese entry page; **`llms.txt`**, a short entry page for machines: what the package
  is, how to install and ask, what it does not contain.
- **Erratum E-0003**: reorganisation conversions use an issuer-specific ex-rights formula.
- **Conformance vectors**: 590 (was 559) — tracking (TRK), discovery (DSC), date formats (DAT); a vector may now
  expect a refusal (`expect.error`).
- **`evals/`**: 14 tasks for testing an assistant that has only the installed package, with expected answers
  generated from the library and a grader.
- **Rule pages**: `scripts/build_site.py` generates one static page per (market family, scope, rule) from the
  data — every record with its interval, value, sources and quotes — and they are published at
  <https://david-marina.github.io/marina-rules/>, rebuilt at each release.
- **`examples/hardcoded_vs_marina.py`**: six fills at rule changes, each computed with today's rule and with the
  rule of the trade date.

### Changed
- Bookkeeping: `cn.fee.commission_min_per_order_cny.2002-05-01` gained `unit: CNY` (the value is unchanged; `diff`
  does not compare `unit` and so does not list it); `hk.order_spread_limit.hk_stock.2025-08-04` listed one source
  twice.
- README, PyPI summary and llms.txt lead with what the package is for — making a backtest checkable by someone else
  (rules by trade date, fill checks with a recomputable stamp, a pinned citation, `as_of`) — and say what a stamp does
  not certify.
- Issue forms for a wrong rule, a missing rule and a rule an exchange has changed; each asks for the official source.
- README states up front that maturity differs by market (A-share, CFFEX, SHFE and INE mostly `verified`; CZCE,
  GFEX, Hong Kong and US mostly `single-source`); more PyPI keywords.
- The weekly source watch checks listing pages only.
- Packaging: the licence metadata names both licences (`MIT AND CC0-1.0`; it said MIT only); the summary, keywords,
  classifiers and project links say what the package covers, in English and Chinese; README links are absolute so
  that they work on the PyPI page.
- Command line: `marina-rules scopes <unknown registry>` exits 2 (it printed `{}`); `marina-rules rules <board
  scope>` adds `see_also` pointing to scope `stock`, where an A-share stock's fees, sessions and holding period are
  recorded; `python -m marina_rules.diff` outside a clone says that it needs one instead of a traceback;
  `marina-check --help` prints the canonical-form lines literally. The command is written `marina-check` throughout
  (some texts said `marina check`, which does not exist).
- **Earlier releases.** 2026.11.13, the first release from this repository, stays on PyPI; its two defects above
  are fixed here, so upgrade unless you are reproducing a result that cites it. 2026.10.26.5 and the releases before
  it are no longer on PyPI, so results that cite them cannot be re-run from there. From now on a published version
  is not deleted.

## [2026.11.13] - 2026-11-13

First release from this repository. The previous release on PyPI was **2026.10.26.5** (since removed from PyPI);
everything below is measured against it. 2026.10.26.6, 2026.10.26.7 and 2026.11.02 were prepared in the previous repository but
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
