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

## [2026.11.23] - 2026-11-23

**In three lines.** *Rules:* no value in force on 2026.11.16 changed; six records were added (SHFE bitumen margin
from 2026-11-17, where 2026.11.16 had a gap, CZCE sunflower seed oil futures, listed 2026-11-12, and how BSE
rounds its limit prices) and two were
raised to `verified`. *Packaging:* the code
moved into its own package, `marina-rules-core` 1.0.0, which this release requires; `pip install -U marina-rules`
installs both, and `import marina_rules`, the three commands and the MCP server work as before. *Corrections:* all in
the code — the fill checker issued its stamp in cases it should not have, and `limit_price` rounded funds and B shares
before 2006-07-01 on a grid Marina has no record of; what to re-run is under marina-rules-core 1.0.0 below.

Dataset: `sha256:3e159d81e1175d71` · 2879 records (1423 `verified`, 1455 `single-source`, 1 `unverified`).

### Corrected (re-run needed)
- **`published_at` of three BSE price-limit records was one day early** (`cn.limit.st_bse.2021-11-15`,
  `cn.limit.delisting_bse.2021-11-15`, `cn.limit.delisting_day1_bse.2021-11-15`): 2021-11-01 → 2021-11-02, the date
  on the announcement (北证公告〔2021〕15号) and on its page. Values and the effective date (2021-11-15) are unchanged.
  Re-run only a query that passes `as_of` 2021-11-01 for these scopes: it was answered as already published and is
  now `NOT_YET_PUBLISHED`.

The other corrections of this week are in the code: see
[marina-rules-core 1.0.0](#marina-rules-core-100---2026-11-23).

### Added
- **SHFE bitumen margin from 2026-11-17** (`cn.futures.margin_ratio.shfe_bu.2026-11-17`, 0.12, `single-source`). The
  general months had been split since 2026-10-12 (gap G-0107, where Marina does not answer) because BU2612 and BU2701
  carried a raised level; BU2611 left the file after 2026-11-16, the two raised contracts became the two nearest
  expiries, which the sample leaves out, and every general month carries 0.12. G-0107 now ends on 2026-11-17. A query
  for `margin_ratio` / `shfe_bu` from that date gets 0.12 instead of `OUT_OF_COVERAGE`.

- **How BSE rounds its limit prices** (`cn.limit.rounding.bse.2021-11-15`, `limit_price_rounding` =
  `toward_prev_close`, `single-source`): limit-up rounded down and limit-down rounded up to CNY 0.01, so that neither
  exceeds the 30% band. The BSE rules give the formula and make any order beyond the band invalid, and - unlike the SSE
  and SZSE rules - say nothing about rounding; the value is read from that, which is why it is `single-source`. The
  exchange's published daily limit prices from 2021-11-15 follow it. Until now Marina had no BSE rounding record and
  `limit_price` rounded BSE prices half up anyway; see marina-rules-core 1.0.0.
- **CZCE sunflower seed oil futures** (scope `czce_so`, listed 2026-11-12; 4 records, all `single-source`):
  trading fee and close-today fee 0.01% of turnover and same-day closing from 2026-11-12, daily band 7% from
  2026-11-13. The values and dates are those of the daily settlement table. CZCE's notice pages cannot be fetched in a
  form that can be hashed and no archived copy exists yet, so what only the listing notice states is a declared gap
  and not a record: the margin (the table shows 8% on every contract, but no citable text fixes where the delivery
  ladder starts; G-0513), the band of the listing day (G-0514) and the session schedule, night session included
  (G-0515).

### Re-verified
- **STAR growth-tier risk disclosure** (`cn.suitability.star_growth_new.2025-07-13`,
  `cn.suitability.star_growth_legacy.2025-07-13`): `single-source` → `verified`. The SSE notice (上证函〔2025〕2218号) is
  the rule text and states the requirement, the exemption and the start date itself; it was re-read on 2026-11-19. The
  records had been held at `single-source` because both texts came from one publisher, which is stricter than the
  definition every other record is held to. A query with `--min verified` now gets these two.
- **Sources added, level unchanged.** The BSE trading rules themselves (北证公告〔2021〕15号, articles 3.3.11 and
  3.3.12) are now cited by the two BSE price-limit records that rested on the exchange's Q&A and drafting note
  (`cn.limit.bse`, `cn.limit.ipo_day1.bse`), and the notice that the risk-warning provisions took effect on
  2026-08-31 (北证公告〔2026〕43号) by `cn.limit.st_bse`. The
  2013 SSE notices behind the bond-ETF and money-market-ETF same-day records (上证基字〔2013〕86号, 上证发〔2013〕9号)
  are no longer on sse.com.cn; they are cited from archived copies of the SSE pages, so the two records stay
  `single-source`. The note of `cn.limit.st_b_share.1998-04-22` now says which of the two start dates in its sources
  is used.
- **Checked, nothing to change.** The 30 China A-share records that were not `verified` were searched again for an
  official text that would settle them. Two were raised (above); for the other 28 no further official text was found,
  and nothing found contradicts a value or a date. The SZSE convertible-bond tick of 2011-02-28 to 2012-12-10
  (`cn.tick.convertible.szse.2011-02-28`) stays `unverified`: the 2011 trading rules (0.001 for bonds) and the 2008
  convertible-bond rules (0.01) still disagree, and no text naming convertible bonds for that period was found.

### Tracked through
- SHFE (XSGE) and INE (XINE): 2026-11-02 → 2026-11-18. Every trading day's settlement and trading parameters were
  compared with the records: no difference outside the listed gaps. The INE notice list refused automated access, so
  INE notices after 2026-11-02 were read only where shfe.com.cn republishes them.
- Hong Kong (XHKG): 2026-11-03 → 2026-11-18. The only rule amendment in the window (uncertificated securities market,
  2026-11-16) restates T+2. The SFC's own news list and HKEX circulars outside the CT series were not read.
- **BSE (BJSE) is tracked for the first time, for its stock-trading scopes** (`bse`, `st_bse`, `delisting_bse`,
  `ipo_day1_bse`, `delisting_day1_bse`, `bse_stock`), through 2026-11-18: the 25 rules in force in BSE's
  trading-management column were read in full and both editions of the trading rules compared article by article;
  no value in the data differs. An open-ended answer for these scopes on or before that date is no longer flagged
  `CARRY_FORWARD_UNTRACKED`. Not covered: superseded editions other than the 2021 trial rules, BSE notices outside
  that column and BSE fee notices; the stamp duty and transfer fee records (scope `stock`, market
  `XSHG+XSHE+BJSE`) stay untracked for a BJSE query.
- US equities (XNYS, XNAS): 2026-11-03 → 2026-11-17. Read: SEC fee-rate advisories (no Section 31 advisory since
  2026-02-27), the FINRA trading-activity-fee page, CAT fee alerts, Nasdaq equity trader alerts and the SEC documents
  in the Federal Register for the window. Not read: NYSE trader updates and FINRA regulatory notices.
- CZCE (XZCE) and GFEX: 2026-11-02 → 2026-11-18. Every trading day's settlement parameters were compared with the
  records: the only changes are the temporary ones Marina does not encode (the day after a one-sided market, the
  ladder before delivery, the doubled band of a newly listed contract). Their notice lists were read for the window.
- Unchanged: CFFEX not tracked.
- **Announced, not yet in the data — US, 2026-12-06.** Overnight ("23/5") trading is scheduled to start on
  2026-12-06: LULD overnight price bands (static, 20%), the Level 3 market-wide halt resuming at 04:00 the next day,
  and a Nasdaq night session 21:00–04:00 (Nasdaq Equity Trader Alert 2026-46 of 2026-08-17 gives 2026-12-06; the
  rule makes the start depend on the consolidated feed being ready). Marina's
  `luld_band` and `extended_hours` records describe the sessions that exist today and cannot yet express an overnight
  session; until they can, an answer for a date from 2026-12-06 is a carry-forward of today's rules.
- **Announced, not yet in the data — GFEX lithium hydroxide futures, 2026-11-26.** Listing notice of 2026-11-13
  (广期所公告〔2026〕71号): margin 11%, band 9% (18% of the benchmark price on the listing day), trading fee
  0.01% of turnover, no close-today fee. No scope exists for it yet; a query is `unsupported`, not answered.
- **Announced, not yet in the data — CAT fee, January 2027.** CAT Fee Alert 2026-3 (2026-11-12) announces CAT Fee
  2027-1 at USD 0.000008 per executed equivalent share for transactions from January 2027 (today 0.000001), subject
  to fee filings that had not been made on 2026-11-19. As with earlier CAT fees, the record is added when the filing
  is published; until then `cat_fee_per_share` for a 2027 date is a carry-forward.

### Changed

- **Two packages.** `marina-rules` (this package, date versions) now holds the dataset and the module
  `marina_rules`, which forwards to the code in `marina-rules-core` (semantic versions; a dependency,
  `marina-rules-core>=1.0.0,<2`). Data releases stay weekly; the code is released when it changes. Nothing to change
  in your code: the import name, the commands `marina-rules`, `marina-check` and `marina-rules-mcp`, `python -m
  marina_rules`, the extra `marina-rules[mcp]` and the MCP registry entry are the same. `marina_rules.__version__` is
  now the code version (`1.0.0`); `marina_rules.VERSION` stays the data version.
- **The citation names both.** `mr.citation()` is `rules: marina-rules@2026.11.23 sha256:3e159d81e1175d71 code:
  marina-rules-core@1.0.0`. To reproduce a result, pin both (`pip install "marina-rules==2026.11.23"
  "marina-rules-core==1.0.0"`). A citation without `code:` comes from a release up to 2026.11.16, which carried its own
  code: `marina-rules==<version>` alone still installs and runs it, also next to a newer `marina-rules-core`.
- `marina_rules` is now a forwarding module: reading, setting and deleting an attribute (`setattr`,
  `monkeypatch.setattr`, `mock.patch`) act on `marina_rules_core`, and `marina_rules.check is marina_rules_core.check`.
  Two things differ from 2026.11.16: writing into its `__dict__` directly (`vars(mr)[...] = …`) has no effect, and
  classes name their new module (`Record.__module__` is `marina_rules_core`), so objects pickled by this release load
  under an older one only where `marina-rules-core` is installed too. Objects pickled by an older release load here.
- A stamp names the data version (`rules-verified@2026.11.23:…`). For a log that none of the corrections below touches,
  the hash after the colon is the one 2026.11.16 issued, since the rules are the same.

### Known issues

What a user of this release should know, in one place.

- **Fixed here, present in 2026.11.13 and 2026.11.16** (neither release is withdrawn; see marina-rules-core 1.0.0):
  stamps issued for logs the checker had not fully checked or whose cells contradicted each other; `limit_price` for
  funds and B shares before 2006-07-01.
- **Fixed in 2026.11.16, present in 2026.11.13:** a date not written `YYYY-MM-DD` selected the wrong rule (in
  practice the newest), and `tick_size` answered 0.01 for instruments without a tick record.
- A-share stocks before 2006-07-01: the tick is not sourced and `limit_price` rounds at 0.01 (known gap G-0005) —
  the only value Marina substitutes.
- **A `scope` cell is checked against what the row says, not against what it leaves out.** A row with
  `scope=main_board` and no ST cell is checked as a non-ST stock; a row with `scope=ipo_first5_main` (no price
  limit) and no listing information is checked as inside its first five days. Nothing in the output marks such a
  row. Give the context you have (`st`, `listing_day_index`, `list_date`) so that the scope can be contradicted —
  or leave the scope cell empty and let the checker choose it from the context, which refuses to guess.
- **`list_date` settles the listing window only at its two ends**: on the date itself (listing day 1) and more than
  60 calendar days after it (past every window). In between, Marina has no trading calendar and a suspension can
  stretch the first five trading days, so a first-five-days scope there is taken as given; `listing_day_index`
  settles it.
- `marina-check` on a log you write yourself reads no quantity, so it cannot reconcile `turnover` with price ×
  quantity (through `--format` the adapter does). A run without `--strict` (the default) uses `unverified` records
  too and is stamped, with a stamp that differs from the `--strict` one.
- Through `--format`, what the adapter reads rests on column names. Two columns it can read as the same field and
  that differ are refused, but a column it does not recognise is not read at all: check `adapter.columns_used` and
  `adapter.columns_not_used` in the output.
- **Two kinds of A-share day have no scope yet**, found by comparing `limit_price` with the limit prices the
  exchanges published from 2018 to 2026 (every other band agreed row for row):
  - *Shares of a company that never completed the 2005–2006 split-share reform* (names prefixed S): SZSE set their
    band at 5% from 2007-01-08 (深证会〔2007〕1号; repealed 2022-03-25, none being left), and the SSE still applies
    5% to the last such stock. Marina answers them as ordinary main-board stocks (10%).
  - *A first trading day that is not an IPO*: a listing by share-swap merger, a listing resumed after suspension, a
    relisting. The trading rules list these among the days with no band, or leave them to the exchange; Marina's
    `ipo_day1_main` (+44% / −36% of the offer price) is for IPOs only, and `listing_day_index` cannot tell them apart.
  Both are planned for a coming release. Until then, do not pass such a row as `main_board` or `ipo_day1_main`.
- Fees: only the statutory floor of A-share stocks (stamp duty and transfer fee) is checked; funds, convertible bonds
  and B shares are not fee-checked.
- Coverage: the Dalian Commodity Exchange (DCE) is not covered; CZCE, GFEX, Hong Kong and US records are mostly
  `single-source`. `coverage()` and `known_gaps()` list every gap Marina knows of.

## [marina-rules-core 1.0.0] - 2026-11-23

**In three lines.** *Code:* the first release of the code as its own package — the functions, checker, adapters,
command line and MCP server of marina-rules 2026.11.16, as the module `marina_rules_core` (and, through marina-rules,
`marina_rules`). *Corrections:* `marina-check` withheld its stamp too rarely, and `limit_price` substituted a tick
where it has none and rounded BSE prices the SSE way; **re-run** any log stamped by 2026.11.13 or 2026.11.16 that one of the items below touches.
*Compatibility:* reads the dataset marina-rules 2026.11.23 or later (data schemas 1, 1.1 and 1.2; releases up to
2026.11.16 carry their own code and are not read by this one); additive, except
that the checker now refuses rows it used to stamp, `limit_price` raises for funds and B shares before 2006-07-01 and gives
BSE limit prices rounded toward the previous close, and
the fee of a fund, convertible bond or B-share row is no longer checked.

### Corrected (re-run needed)

`marina-check` / `check_rows` issued a `rules-verified` stamp in cases where it should have withheld it. Three were
reported by an outside tester; two independent reviews of the fix found more of the same kind. All of them are
present in 2026.11.13 and 2026.11.16. The principle behind every item: a changed standard, inputs that contradict each
other, and input that cannot be read never get the stamp a complete, valid check gets. **Re-run** any log those
releases stamped; a stamp from them is not evidence of compliance where one of the cases below applies.

*Limit prices*

- **BSE limit prices were rounded half up, with no record behind it, and were wrong by CNY 0.01 on about half of
  the trading days.** `limit_price` rounded every market half up; only SSE and SZSE have a rounding record. It now
  reads `limit_price_rounding` for the market (BSE: toward the previous close, `cn.limit.rounding.bse.2021-11-15`)
  and raises `KeyError` where none is in force. Example: previous close 12.86 gives 16.71 / 9.01 (was 16.72 / 9.00).
  **Re-run** any BSE limit price taken from `limit_price`, and any `marina-check` run on BSE fills: a fill at the old
  limit-up price was passed and is now flagged (`PRICE_OUTSIDE_BAND`; a buy also
  `LIMIT_BUY_ABOVE_UP`).

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
  the instrument family and the dates that do have a record (the MCP tool `limit_price` reports "not answered";
  `marina-check` reports `RULE_MISSING` for the row, so the log is not verified). Pass `decimals` only
  if you know the grid the exchange used — in `marina-check` that makes the run relaxed. The 0.01 substitution now
  applies to an A-share stock scope on a date before the first stock tick record, and to nothing else. From
  2006-07-01 one call changed: with a market naming both exchanges, `limit_price(…, "b_share", …, "XSHG+XSHE")`
  also fell back to 0.01 — right for Shenzhen (0.01 HKD), wrong for Shanghai (0.001 USD) — and now raises
  `RuleConflict`, which says to name one exchange; where both exchanges record the same tick (funds, stocks) the
  combined market is answered as before. **Re-run** anything that took fund or B-share limit prices before
  2006-07-01, or B-share limit prices under a combined market, from Marina.

*Inputs that contradict each other*

- **An explicit `scope` overrode what the row itself said about the instrument.** A row with `scope=main_board` and
  `st_status=true` was checked against the ordinary 10 % band and stamped, although `resolve()` refuses the same
  context. A row that names a scope is now compared with that scope's `asserts` in the registry, using the context
  cells the row supplies (every key a scope requires or asserts, the fund keys such as `fund_constituents`
  included), `list_date` where it decides the listing-day index, and the board of a recognised A-share stock code
  when the row has no `board` cell (`scope=ipo_first5_main` on a ChiNext code). A contradiction is the new finding
  `SCOPE_CONTEXT_CONFLICT` and no other check runs on the row. A key the row leaves out is not demanded.
  The same finding covers the kind of instrument: a recognised A-share stock code under a scope that is not a stock
  scope (`600000` with `scope=convertible` was checked against the convertible band — unlimited before 2022 — and
  stamped), a 900… / 200… B-share code under a scope that is not a B-share scope, and a fund or bond code (5xxxxx,
  1xxxxx) under a stock scope (`510300` with `scope=main_board` had its limits rounded at 0.01 instead of 0.001).
  A `list_date` close to the trade also counts where it settles the matter without a calendar: a day after it is
  not listing day 1, so a listing-day scope is refused, and a registration-regime main-board row two to four days
  after its `list_date` cannot be `scope=main_board`.
- **Two cells of one row that state different things.** Columns `st` and `st_status` with different values (the
  later column used to win); a `market` or `board` cell that names another exchange or board than a recognised
  stock code (`600000` with `market=XSHE`), or another exchange than a 900… / 200… B-share code (in any
  spelling: `900901`, `sh900901`, `900901.SH`); a code whose own suffix or prefix names another exchange than its
  digits or than the `market` cell (`600000.SZ`, `510300.SZ` with `market=XSHG`); a trade dated before its own
  `list_date`. All are `ROW_INVALID`. A `market` cell is read in any case (`xshg`).
- **The adapter settled such contradictions before the checker saw them.** Through `--format` (and
  `marina-rules adapt`), a table with two columns for one field — an `st` and an `is_st`, a `prev_close` and a
  `pre_close`, a `date` and a `trade_date`, a `price` and a `trade_price`, a `fee` and a `fees`, vn.py's `symbol`
  and `vt_symbol`, or one name in two spellings (`prev_close` and `PREV_CLOSE`) — was read from the first of the
  two and stamped; a value in the fills silently won over a different one in the `--bars`, `--st` or `--listing`
  table; a code suffix that named another exchange than the exchange column was counted but the row went on; a
  turnover that was not price × quantity was taken as written, which lowers the fee floor the row is held to. The
  adapter now writes the reason into a new output column, `row_error`, which the checker reports as `ROW_INVALID`;
  the adapter's report counts these rows under `rows_refused` and lists the columns it did not read under
  `columns_not_used`. `--map field=COLUMN` says which of two columns a field is. Two cells that say the same thing
  in another spelling (`0` / `false`, `SSE` / `XSHG`, `20000101` / `2000-01-01`), a quantity in lots of 10 or 100,
  and a second column that cannot be read as the field at all (a `market` column holding a board name) are not a
  conflict. A file that names a column twice (RQAlpha writes `datetime` twice) is refused row by row where the two
  cells differ.
- **A joined table that did not say one thing was used anyway.** An `--st` table with a row that could not be read
  still counted its day as covered, so the security came out "not ST"; with two answers for one security and day,
  or a `--listing` table with two dates for one security, the last row won. Each now stops the run (exit code 2),
  as two bars for one security and day already did. A bar's ST cell that cannot be read is passed through, not
  dropped. Bars of the same six digits on two exchanges (`000001.SH` the index, `000001.SZ` the stock) are two
  securities instead of an error.
- **Rows of one code on one day that disagree** on the previous close or the scope: the later row gets the new
  finding `ROWS_DISAGREE`. `600000`, `600000.SH`, `sh600000` and `SHSE.600000` are one code for this purpose; a row
  that names no market is compared with the others of its digits, and rows that name different markets are
  different instruments.

*Input that cannot be read*

- **An unreadable `fee` or `turnover` skipped the fee check.** `fee=0` is `FEE_BELOW_STATUTORY`, but `fee=nan`,
  `inf` or any text was read as "no fee given" and passed, stamped; so did `turnover=nan`. A cell that is present
  but not a finite number (and a negative turnover) is now `ROW_INVALID`. The adapter (`--format`,
  `marina-rules adapt`) used to drop such a cell before the checker saw it; it now passes an unreadable fee,
  turnover, ST or listing-date cell through as written and counts it under `cells_not_read`. An absent cell still
  means no fee check, and the output now says so: `fee_check` counts `rows_checked` and `rows_not_checked`, and a
  stamp says nothing about the fees of the latter. Behind the adapter the same applies to the quantity: when the
  turnover has to be formed from price × quantity and the quantity cell cannot be read, the row is refused
  (`row_error`) instead of losing its fee check.
- **A column whose name had a space around it, or was written in another case, was not read.** A header written
  `fee `, ` turnover`, `Fee` or `ST` was ignored by the checks — `fee=0` under it passed, stamped; the space
  variants were not even listed in `columns_not_read`. Column names are now read in any case and without
  surrounding white space; two columns that are one name by that rule and both hold a value, a different one each,
  are `ROW_INVALID` (where one of them is empty the other is the value). The MCP tool `check_fills` merged such
  columns before the checker saw them, the last one winning; it now passes them on as written.
- A `price` or `prev_close` that is zero or negative (a zero price against a zero previous close used to pass), an
  empty `code`, a `list_date` that is not a date, and a `date` with anything but a time after the day
  (`2024-03-01XYZ`, `2024-03-01 XYZ`, `2024-03-01Tjunk`) are `ROW_INVALID` — also behind the adapter, whose date
  reader accepted any tail and handed the checker a clean date. The time is exchange time: a UTC offset other than
  `+08:00` (`…T20:31:00-05:00`, `…Z`) could put the trade on another day there and is refused. A row without a date
  is `ROW_INVALID` too (with scope context and no scope it used to raise `ValueError`). In Python, a `float('nan')`
  in `fee` or `turnover` — what `DataFrame.to_dict("records")` gives for a missing value — is such an unreadable
  cell: write `None` or leave the key out for "no fee given"
  (`df.astype(object).where(df.notna(), None).to_dict("records")`, for `check_rows` and `adapt_rows` alike).
- `marina-check FILLS.csv` refuses a header that names a column twice (exit code 2): the second `fee` column
  silently replaced the first.

Stamps of logs that none of the above touches are unchanged: the canonical form and its version are the same.

**Not changed, so that it is not mistaken for checked:** on a log you write yourself `turnover` is not reconciled
with price × quantity (the checker reads no quantity; the adapter does); a column the checker does not read
(`is_st`, `note`) is ignored, and is now listed in `columns_not_read`; a run without `--strict` (`strict=False`,
the default) can still be stamped, with a stamp that differs from the `--strict` one; a `scope` cell is compared
with the context the row gives, and a row that gives none is taken at its word (see Known issues above).

### Changed

- A trade dated on its `list_date` is listing day 1 (`listing_index_from_list_date` returns 1): with
  `issue_regime` given, such a row gets its listing-day scope instead of `SCOPE_UNDETERMINED`.
- `fee_check` counts a row as checked only when the statutory floor for its date was found; `tracking` counts only
  rows the checks ran on. A B-share row without a market is `MARKET_REQUIRED` instead of an uncaught `RuleConflict`.
- The fee floor is applied to A-share stock scopes only. It is the stamp duty and transfer fee of stocks, and was
  also held against funds, convertible bonds and B shares, which pay other charges: an ETF sale with a correct fee
  was `FEE_BELOW_STATUTORY`. Such rows are now counted in `fee_check.rows_not_checked`.
- A row whose `market` cell names both exchanges (`XSHG+XSHE`) and whose code is a recognised stock code is checked
  under the code's own exchange (a 900… / 200… B-share code included). The one-tick floor differs by exchange
  before 2023-04-10, and the combined cell was read as the Shanghai rule, so a valid Shenzhen fill at a very low
  price could be reported as beyond its limit. On a code that does not say which exchange it is, a combined cell is
  `MARKET_REQUIRED` where the tick differs by exchange (B shares; convertible bonds before 2022-08-01): such a row
  used to pass with its price grid unchecked.
- Rule pages (the generated site) can be found in Chinese. Every page has a Chinese name in its title, its
  description and a line under the heading — `创业板涨跌幅限制：10%→20%，2020-08-24 起 · price_limit_pct · chinext …`
  — and the family tables list each scope's Chinese name. The names are display names kept in
  `scripts/site_zh.json`; the values in that line are the page's own record values in `effective_from` order,
  written only where the records are plain values in an unbroken series that is still in force — one series, or
  one per exchange (237 of 479 pages; 230 of them have one series and carry the value in the title) — with the
  exchanges named at each step when a rule was later extended to another exchange. The line says where the records
  begin; a title gives a date only for a change of value. Each page also carries Open Graph tags, and the
  index and every rule page a schema.org `Dataset` description (JSON-LD: name, description, licence, version,
  temporal coverage, the official source URLs under `isBasedOn`). The pages still run no script. `llms.txt` lists
  the Chinese name after each link, and each `.md` page repeats the Chinese line.
- `README.md` opens with the Chinese summary (it is the PyPI project description); `CITATION.cff` added.

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
